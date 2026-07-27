"""ArtifactStore — versioned, sprint-scoped artifact persistence.

Base path layout::

    {workspace_root}/{project_id}/artifacts/
        project/
            domain.json
            user_stories.json          ← base version
            user_stories_v2.json       ← incremented on version=True
        sprint_1/
            tasks.json
            qa_findings.json
        sprint_2/
            ...
        release/
            regression_qa.json

No external dependencies — stdlib only (json, pathlib, logging, re).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Regex that matches versioned filenames: name_v<N>.json
_VERSION_RE = re.compile(r"^(.+)_v(\d+)\.json$")

# Valid scope names (open-ended for sprint_N variants)
_SCOPE_PROJECT = "project"
_SCOPE_RELEASE = "release"


class ArtifactStore:
    """Read/write JSON artifacts scoped by project phase or sprint number.

    Parameters
    ----------
    workspace_root:
        The top-level workspace directory (e.g. ``Path("temp-workspace")``).
    project_id:
        The project identifier.  All artifacts are stored under
        ``workspace_root / project_id / "artifacts" / <scope> / <name>.json``.
    """

    def __init__(self, workspace_root: Path, project_id: str) -> None:
        self._base = workspace_root / project_id / "artifacts"
        self._project_id = project_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scope_dir(self, scope: str) -> Path:
        """Return (and create if needed) the directory for *scope*."""
        path = self._base / scope
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _base_file(self, scope: str, name: str) -> Path:
        """Return the canonical (unversioned) file path for *scope*/*name*."""
        return self._scope_dir(scope) / f"{name}.json"

    def _latest_version(self, scope: str, name: str) -> Path | None:
        """Return the path to the highest-versioned file (or the base file).

        Search order:
        1. If versioned files exist (``name_v2.json``, ``name_v3.json`` …),
           return the one with the highest version number.
        2. Otherwise, if the base file (``name.json``) exists, return it.
        3. Return ``None`` if nothing exists.
        """
        scope_dir = self._scope_dir(scope)
        base_file = scope_dir / f"{name}.json"

        highest_ver: int = 0
        highest_path: Path | None = None

        for p in scope_dir.glob(f"{name}_v*.json"):
            m = _VERSION_RE.match(p.name)
            if m and m.group(1) == name:
                ver = int(m.group(2))
                if ver > highest_ver:
                    highest_ver = ver
                    highest_path = p

        if highest_path is not None:
            return highest_path
        if base_file.exists():
            return base_file
        return None

    def _next_version_path(self, scope: str, name: str) -> Path:
        """Return the path for the *next* version of *name* in *scope*.

        If ``name.json`` exists and no versioned files exist, the next
        version is ``name_v2.json``.  The counter increments from there.
        """
        scope_dir = self._scope_dir(scope)
        base_file = scope_dir / f"{name}.json"

        if not base_file.exists():
            # No base file at all — just write the canonical base name.
            return base_file

        # Scan for existing versioned files.
        highest_ver: int = 1  # base counts as v1
        for p in scope_dir.glob(f"{name}_v*.json"):
            m = _VERSION_RE.match(p.name)
            if m and m.group(1) == name:
                ver = int(m.group(2))
                if ver > highest_ver:
                    highest_ver = ver

        return scope_dir / f"{name}_v{highest_ver + 1}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        scope: str,
        name: str,
        data: dict,
        version: bool = False,
    ) -> Path:
        """Persist *data* as JSON under *scope*/*name*.

        Parameters
        ----------
        scope:
            ``"project"``, ``"sprint_1"``, ``"sprint_2"``, ``"release"``, etc.
        name:
            Artifact name without extension (e.g. ``"user_stories"``).
        data:
            JSON-serialisable dictionary to persist.
        version:
            When ``True`` and the base file already exists, writes a new
            incremented version file instead of overwriting.  The base file
            is always the *first* write; ``_v2``, ``_v3`` … follow.

        Returns
        -------
        Path
            The path of the file that was written.
        """
        if version:
            target = self._next_version_path(scope, name)
        else:
            target = self._base_file(scope, name)

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug(
            "[ArtifactStore] wrote %s/%s → %s",
            scope,
            name,
            target.relative_to(self._base),
        )
        return target

    def read(self, scope: str, name: str) -> dict | None:
        """Return the latest version of *scope*/*name*, or ``None`` if absent.

        "Latest" means the highest version number when versioned files exist,
        falling back to the base (unversioned) file.
        """
        path = self._latest_version(scope, name)
        if path is None:
            logger.debug("[ArtifactStore] read miss: %s/%s", scope, name)
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[ArtifactStore] failed to read %s/%s from %s: %s",
                scope,
                name,
                path,
                exc,
            )
            return None

    def exists(self, scope: str, name: str) -> bool:
        """Return ``True`` if *any* version of *scope*/*name* exists on disk."""
        return self._latest_version(scope, name) is not None

    def list_scope(self, scope: str) -> list[str]:
        """Return the base names of all artifacts written under *scope*.

        Versioned files (``name_v2.json``) are collapsed back to their base
        name (``name``) so each logical artifact appears exactly once.
        """
        scope_dir = self._base / scope
        if not scope_dir.exists():
            return []

        names: set[str] = set()
        for p in scope_dir.glob("*.json"):
            m = _VERSION_RE.match(p.name)
            if m:
                names.add(m.group(1))
            else:
                names.add(p.stem)
        return sorted(names)

    def append_version_audit(
        self,
        artifact_name: str,
        new_version: str,
        reason: str,
        bug_analysis_type: str,
        sprint: int,
        iteration: int,
    ) -> None:
        """Append one entry to artifacts/project/version_history.json.

        Records when and why an artifact was versioned.

        Parameters
        ----------
        artifact_name : str
            Name of the artifact that was versioned (e.g., "user_stories").
        new_version : str
            Version string (e.g., "v2", "v3").
        reason : str
            Why the artifact was updated (e.g., bug fix instruction).
        bug_analysis_type : str
            Type of bug that triggered the update ("spec_bug", "architecture_bug").
        sprint : int
            Sprint number (0 if not in a sprint).
        iteration : int
            Which iteration of updates this was.
        """
        history_path = self._scope_dir("project") / "version_history.json"
        history = []

        if history_path.exists():
            try:
                history = json.loads(history_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("[ArtifactStore] failed to read version_history: %s", exc)
                history = []

        history.append({
            "artifact": artifact_name,
            "version": new_version,
            "reason": reason,
            "bug_type": bug_analysis_type,
            "sprint": sprint,
            "iteration": iteration,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        try:
            history_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
            logger.debug(
                "[ArtifactStore] appended version audit for %s → %s",
                artifact_name,
                new_version,
            )
        except Exception as exc:
            logger.warning("[ArtifactStore] failed to write version_history: %s", exc)
