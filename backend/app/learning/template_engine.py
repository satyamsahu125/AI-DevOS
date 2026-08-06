from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(os.getenv("LEARNING_DB", "data/learning.sqlite"))

# Keys whose values are project-specific and should be replaced with
# placeholders when extracting a template from a concrete artifact.
_VOLATILE_KEYS = frozenset({
    "project_id",
    "project_name",
    "sprint",
    "sprint_number",
    "created_at",
    "updated_at",
    "timestamp",
    "run_id",
    "request_id",
})

_PLACEHOLDER = "__TEMPLATE_VALUE__"


@dataclass
class Template:
    """Structural skeleton of an approved artifact for one stage."""

    template_id: str
    stage: str
    structure: dict        # project-specific values replaced with _PLACEHOLDER
    source_project_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TemplateEngine:
    """Extracts reusable structural templates from approved artifacts and
    injects them into new stage runs.

    DESIGN:
    - Templates are derived from approved artifacts by stripping project-
      specific leaf values and keeping the structural skeleton (key hierarchy,
      list cardinality, type shapes).
    - Stored in the same SQLite database as the LearningLoop (LEARNING_DB).
    - find_similar() performs a lightweight key-set overlap search — no
      vector embeddings, keeping this module dependency-free.
    - inject_template() merges a stored skeleton with the concrete context
      values for the current run; callers can use the result as a prompt
      hint to steer the LLM toward an established structure.

    INTENDED USE:
      1. WorkflowEngine calls extract_template() after a stage is approved.
      2. Before the next run of the same stage, find_similar() returns the
         closest stored template.
      3. inject_template() merges it with the new context and the result is
         appended to the stage prompt by the agent.

    Contract: all public methods are non-fatal — errors are logged and a
    safe empty result is returned.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._ensure_schema()
        logger.debug("template_engine ready: db=%s", self._db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_template(self, artifact: dict, stage: str, project_id: str = "") -> Template:
        """Derive a structural skeleton from artifact and persist it.

        Volatile keys (project_id, timestamps, etc.) are replaced with
        ``_PLACEHOLDER`` so the template captures structure, not data.
        Returns the persisted Template.
        """
        try:
            skeleton = self._to_skeleton(artifact)
            template = Template(
                template_id=str(uuid.uuid4()),
                stage=stage,
                structure=skeleton,
                source_project_id=project_id,
            )
            self._store(template)
            logger.info(
                "template_engine.extract_template: stage=%s project=%s template_id=%s",
                stage, project_id, template.template_id,
            )
            return template
        except Exception as exc:
            logger.warning("extract_template failed for stage=%s: %s", stage, exc)
            return Template(
                template_id=str(uuid.uuid4()),
                stage=stage,
                structure={},
                source_project_id=project_id,
            )

    def find_similar(self, stage: str, context: dict, limit: int = 3) -> list[Template]:
        """Return up to limit templates for stage, ranked by key-set overlap with context.

        Key-set overlap is computed as |template_keys ∩ context_keys| /
        |template_keys ∪ context_keys|.  Returns most-overlapping first.
        Falls back to recency (most recent first) when overlap ties.
        """
        try:
            rows = self._conn.execute(
                "SELECT template_id, stage, structure, source_project_id, created_at "
                "FROM templates WHERE stage = ? ORDER BY created_at DESC LIMIT 50",
                (stage,),
            ).fetchall()
            if not rows:
                return []

            context_keys = set(self._flatten_keys(context))
            scored: list[tuple[float, Template]] = []
            for template_id, s, structure_json, source_project_id, created_at_str in rows:
                try:
                    structure = json.loads(structure_json)
                except Exception:
                    structure = {}
                template_keys = set(self._flatten_keys(structure))
                union = template_keys | context_keys
                overlap = len(template_keys & context_keys) / max(len(union), 1)
                created_at = datetime.fromisoformat(created_at_str)
                template = Template(
                    template_id=template_id,
                    stage=s,
                    structure=structure,
                    source_project_id=source_project_id,
                    created_at=created_at,
                )
                scored.append((overlap, template))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [t for _, t in scored[:limit]]
        except Exception as exc:
            logger.warning("find_similar failed for stage=%s: %s", stage, exc)
            return []

    def inject_template(self, template: Template, context: dict) -> dict:
        """Merge template skeleton with concrete context values.

        Returns a dict where:
        - Keys present in context use the context value (concrete project data).
        - Keys absent from context but in the template retain _PLACEHOLDER
          to signal "this key is expected — fill it in".
        - Result is a shallow-merged union of template structure and context.

        Callers can serialize this dict and include it in the stage prompt
        as a "structural hint" for the LLM.
        """
        try:
            merged = self._deep_merge(template.structure, context)
            logger.debug(
                "inject_template: stage=%s template_id=%s merged_keys=%d",
                template.stage, template.template_id, len(merged),
            )
            return merged
        except Exception as exc:
            logger.warning("inject_template failed for template_id=%s: %s", template.template_id, exc)
            return dict(context)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS templates (
                template_id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                structure TEXT NOT NULL,
                source_project_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _store(self, template: Template) -> None:
        self._conn.execute(
            "INSERT INTO templates (template_id, stage, structure, source_project_id, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                template.template_id,
                template.stage,
                json.dumps(template.structure),
                template.source_project_id,
                template.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def _to_skeleton(self, obj: Any, depth: int = 0) -> Any:
        """Recursively replace leaf values with _PLACEHOLDER.

        Volatile keys are replaced at any depth.  Lists are preserved as
        single-element representative samples (cardinality hint only).
        """
        if depth > 10:
            return _PLACEHOLDER
        if isinstance(obj, dict):
            result: dict = {}
            for k, v in obj.items():
                if k in _VOLATILE_KEYS:
                    result[k] = _PLACEHOLDER
                else:
                    result[k] = self._to_skeleton(v, depth + 1)
            return result
        if isinstance(obj, list):
            if not obj:
                return []
            # Keep one representative element to preserve structure hint
            return [self._to_skeleton(obj[0], depth + 1)]
        # Leaf value — replace with placeholder
        return _PLACEHOLDER

    def _flatten_keys(self, obj: Any, prefix: str = "") -> list[str]:
        """Return a flat list of dotted key paths for overlap scoring."""
        keys: list[str] = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                full = f"{prefix}.{k}" if prefix else k
                keys.append(full)
                keys.extend(self._flatten_keys(v, full))
        elif isinstance(obj, list) and obj:
            keys.extend(self._flatten_keys(obj[0], prefix))
        return keys

    def _deep_merge(self, template: Any, context: Any) -> Any:
        """Merge context values into template skeleton recursively."""
        if isinstance(template, dict) and isinstance(context, dict):
            merged: dict = {}
            all_keys = set(template) | set(context)
            for k in all_keys:
                if k in context and k in template:
                    merged[k] = self._deep_merge(template[k], context[k])
                elif k in context:
                    merged[k] = context[k]
                else:
                    merged[k] = template[k]
            return merged
        # If context provides a concrete value, use it; otherwise keep template
        if context is not None and context != _PLACEHOLDER:
            return context
        return template
