"""BlueprintStore — three-layer persistence for architect blueprint data.

Layer 1: disk       — project/{id}/project/blueprint.json (survives session end)
Layer 2: memory_manager — fast KV access during generation
Layer 3: learning_loop  — cross-project learning after QA outcome
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class BlueprintStore:
    """Persists and retrieves blueprint data across three storage layers.

    Parameters
    ----------
    memory_manager:
        KV store — used for fast in-session blueprint reads by ContextAssembler.
    workspace_manager:
        Provides the project workspace path for disk writes.
    learning_loop:
        Optional — records blueprint outcomes for cross-project learning.
        If None, Layer 3 is silently skipped.
    """

    _MEMORY_KEY = "blueprint:latest"

    def __init__(
        self,
        memory_manager: Any = None,
        workspace_manager: Any = None,
        learning_loop: Any = None,
    ) -> None:
        self._memory = memory_manager
        self._workspace = workspace_manager
        self._learning_loop = learning_loop

    def save(self, project_id: str, architect_output: dict) -> None:
        """Persist architect output to disk and MemoryManager (Layers 1 and 2).

        Call this immediately after the Architect stage completes.
        architect_output is the structured_content dict from the Architect artifact.

        Parameters
        ----------
        project_id:
            Project identifier.
        architect_output:
            The full JSON dict produced by the Architect agent.
        """
        payload = {
            **architect_output,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

        # Layer 1 — disk
        try:
            if self._workspace is not None:
                workspace_path = self._workspace.get_workspace_path(project_id)
                project_dir = workspace_path / "project"
                project_dir.mkdir(parents=True, exist_ok=True)
                blueprint_path = project_dir / "blueprint.json"
                blueprint_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                logger.info(
                    "[BlueprintStore] blueprint written to disk: project=%s path=%s",
                    project_id, blueprint_path,
                )
        except Exception as exc:
            logger.warning(
                "[BlueprintStore] disk write failed (non-fatal): project=%s error=%s",
                project_id, exc,
            )

        # Layer 2 — MemoryManager
        try:
            if self._memory is not None:
                self._memory.store(project_id, self._MEMORY_KEY, json.dumps(payload))
                logger.info(
                    "[BlueprintStore] blueprint stored in memory: project=%s", project_id,
                )
        except Exception as exc:
            logger.warning(
                "[BlueprintStore] memory write failed (non-fatal): project=%s error=%s",
                project_id, exc,
            )

    def get(self, project_id: str) -> dict | None:
        """Read blueprint from MemoryManager, falling back to disk.

        Returns the blueprint dict, or None if not found in either layer.
        """
        # Try Layer 2 first — faster
        try:
            if self._memory is not None:
                raw = self._memory.load(project_id, self._MEMORY_KEY)
                if raw:
                    return json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:
            logger.debug("[BlueprintStore] memory read failed, trying disk: %s", exc)

        # Fall back to Layer 1 — disk
        try:
            if self._workspace is not None:
                workspace_path = self._workspace.get_workspace_path(project_id)
                blueprint_path = workspace_path / "project" / "blueprint.json"
                if blueprint_path.exists():
                    return json.loads(blueprint_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug("[BlueprintStore] disk read failed: %s", exc)

        logger.warning(
            "[BlueprintStore] blueprint not found in memory or disk: project=%s", project_id,
        )
        return None

    def record_outcome(
        self,
        project_id: str,
        outcome: str,
        failure_reason: str | None = None,
    ) -> None:
        """Record QA outcome to LearningLoop (Layer 3).

        Call after QA stage completes. outcome is "success", "partial", or "failed".
        If learning_loop is not wired, this is a no-op.

        Parameters
        ----------
        project_id:
            Project identifier.
        outcome:
            "success" | "partial" | "failed"
        failure_reason:
            Optional description of what broke, for failed/partial outcomes.
        """
        if self._learning_loop is None:
            return

        blueprint = self.get(project_id)
        if blueprint is None:
            logger.warning(
                "[BlueprintStore] record_outcome: no blueprint found for project=%s", project_id,
            )
            return

        lesson = {
            "project_type": blueprint.get("project_type", "unknown"),
            "framework": (
                blueprint.get("tech_stack", {}).get("backend")
                if isinstance(blueprint.get("tech_stack"), dict)
                else blueprint.get("framework", "unknown")
            ),
            "dependencies": {
                d["name"]: d["version"]
                for d in blueprint.get("dependencies", [])
                if isinstance(d, dict) and "name" in d and "version" in d
            },
            "folder_structure": [
                node.get("path") for node in blueprint.get("folder_structure", [])
                if isinstance(node, dict)
            ],
            "constraints": blueprint.get("constraints", []),
            "outcome": outcome,
            "failure_reason": failure_reason,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            if hasattr(self._learning_loop, "record_lesson"):
                self._learning_loop.record_lesson(
                    stage="Architect",
                    project_id=project_id,
                    what_worked=f"project_type={lesson['project_type']} framework={lesson['framework']} outcome={outcome}",
                    what_failed=failure_reason or "",
                    reviewer_said=json.dumps(lesson),
                )
            elif hasattr(self._learning_loop, "record_trajectory"):
                from .learning_loop import Trajectory
                traj = Trajectory(
                    stage="Architect",
                    task_description=f"project_type={lesson['project_type']} framework={lesson['framework']}",
                    artifact_summary=json.dumps(lesson),
                    retry_count=0,
                    approved=(outcome == "success"),
                    reviewer_feedback=failure_reason or "",
                    agent_model="",
                    tokens_used=0,
                    latency_ms=0.0,
                    project_id=project_id,
                )
                self._learning_loop.record_trajectory(traj, project_id=project_id)
            elif hasattr(self._learning_loop, "record"):
                self._learning_loop.record(
                    stage="Architect",
                    project_id=project_id,
                    what_worked=f"project_type={lesson['project_type']} framework={lesson['framework']} outcome={outcome}",
                    what_failed=failure_reason or "",
                    reviewer_said=json.dumps(lesson),
                )
            logger.info(
                "[BlueprintStore] blueprint lesson recorded: project=%s outcome=%s",
                project_id, outcome,
            )
        except Exception as exc:
            logger.warning(
                "[BlueprintStore] learning_loop record failed (non-fatal): project=%s error=%s",
                project_id, exc,
            )
