"""ProgressTracker — single responsibility: compute pipeline progress percentage.

Extracted from WorkflowEngine._compute_progress_percent.  Reads project state
from workspace and returns an integer 0–100.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Stages that are added implicitly once the pipeline is past the Q&A phase.
_PRE_PIPELINE: list[str] = ["DomainResearch", "Clarifying"]

# Sub-stages that exist within each sprint but are not in the main Stage enum.
_SPRINT_SUB: list[str] = [
    "ScrumMaster",
    "FileStructurePlanner",
    "BackendDeveloper",
    "FrontendDeveloper",
    "SprintDeploy",
    "SprintReview",
]

# States that imply all sprints are done.
_POST_SPRINT: frozenset[str] = frozenset({
    "all_sprints_complete",
    "qa_complete",
    "deployable",
    "done",
    "resuming_from_change",
})

# Total assumed stage count (matches the 20-stage STAGES array the frontend uses).
_TOTAL_STAGES: int = 20


class ProgressTracker:
    """Computes 0–100 progress for a project by inspecting its workspace state.

    Parameters
    ----------
    workspace_manager:
        Provides load_project_json(project_id) → dict | None.
    """

    def __init__(self, workspace_manager: Any) -> None:
        self._workspace = workspace_manager

    def compute(self, project_id: str) -> int:
        """Return progress percentage (0–100) for project_id."""
        try:
            data = self._workspace.load_project_json(project_id) or {}
            state_str = data.get("state", "")
            completed: list[str] = list(data.get("stages_completed", []))

            # Inject implied pre-pipeline stages once past EMPTY/not_started.
            if state_str not in ("", "empty", "not_started"):
                for s in _PRE_PIPELINE:
                    if s not in completed:
                        completed.append(s)

            # Inject sprint sub-stages once past the sprint phase.
            if state_str in _POST_SPRINT:
                for s in _SPRINT_SUB:
                    if s not in completed:
                        completed.append(s)

            if state_str in ("deployable", "done"):
                return 100

            return round(100 * len(completed) / _TOTAL_STAGES) if completed else 0
        except Exception as exc:
            logger.debug("ProgressTracker.compute failed for %s: %s", project_id, exc)
            return 0
