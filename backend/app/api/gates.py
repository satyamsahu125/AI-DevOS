"""Human collaboration gates API.

Provides structured pause points where a human can review and approve
pipeline artifacts before expensive phases continue.

Gates:
  - /architecture  — after Architect stage; review before Designer runs
  - /design        — after Designer stage; review before Security runs
  - /sprint-plan   — after SprintPlanner stage; review before sprint execution

All gate endpoints run on the calling thread — they are fast (state transition
+ optional stage re-run scheduling) and do not need async task queuing yet.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..shared.dto.gate_result import GateResult
from ..shared.enums.project_state import ProjectState
from ..shared.enums.stage import Stage
from .dependencies import get_artifact_manager, get_container, get_workspace_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workflow/{project_id}/gates", tags=["gates"])

# Map from gate name → ProjectState when gate is pending
_GATE_STATES = {
    "architecture": ProjectState.ARCHITECTURE_REVIEW_PENDING,
    "design":       ProjectState.DESIGN_REVIEW_PENDING,
    "sprint_plan":  ProjectState.SPRINT_PLAN_REVIEW_PENDING,
}

# Map from gate name → Stage enum (artifact to load and possibly re-run)
_GATE_STAGES = {
    "architecture": Stage.Architect,
    "design":       Stage.Designer,
    "sprint_plan":  Stage.SprintPlanning,
}

# Map from gate → next state after approval
_GATE_NEXT_STATES = {
    "architecture": "architecture_ready",  # pipeline resumes from Discovery
    "design":       "design_approved",     # pipeline resumes at Security
    "sprint_plan":  "sprint_plan_ready",   # pipeline resumes at sprint execution
}

# Map from gate → next stage description
_GATE_NEXT_STAGES = {
    "architecture": "Designer",
    "design":       "Security",
    "sprint_plan":  "Sprint Execution",
}


class ReviseRequest(BaseModel):
    feedback: str


class AdjustRequest(BaseModel):
    feedback: str = ""
    max_sprints: int | None = None


# ─────────────────────────────────────────────────────────────────────────────
# GET /workflow/{project_id}/gates/current
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/current")
def get_current_gate(
    project_id: str,
    workspace=Depends(get_workspace_manager),
    artifact_manager=Depends(get_artifact_manager),
) -> dict[str, Any]:
    """Return the currently active gate for a project (if any).

    The frontend polls this to know which review panel to show and what
    artifact to render for the human reviewer.
    """
    state = workspace.get_state(project_id)
    gate = _state_to_gate(state)
    if gate is None:
        return {"gate": None, "state": state.value if hasattr(state, "value") else str(state)}

    artifact_struct: dict = {}
    stage_enum = _GATE_STAGES.get(gate)
    if stage_enum and artifact_manager:
        try:
            art = artifact_manager.get_artifact(project_id, stage_enum)
            if art:
                artifact_struct = getattr(art, "structured_content", None) or {}
                if not artifact_struct and art.content:
                    try:
                        artifact_struct = json.loads(art.content)
                    except Exception:
                        artifact_struct = {"raw": art.content}
        except Exception as exc:
            logger.warning("gates.get_current_gate: artifact load failed for %s/%s: %s", project_id, gate, exc)

    return {
        "gate": gate,
        "state": state.value if hasattr(state, "value") else str(state),
        "artifact": artifact_struct,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Architecture gate
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/architecture/approve")
def approve_architecture(
    project_id: str,
    workspace=Depends(get_workspace_manager),
    container=Depends(get_container),
) -> dict[str, Any]:
    """Approve the architecture. Transitions state and schedules pipeline resume."""
    _assert_gate_state(project_id, "architecture", workspace)
    workspace.update_state(project_id, ProjectState.ARCHITECTURE_READY)
    _schedule_resume(project_id, container)
    return GateResult(
        status="resumed",
        project_id=project_id,
        gate="architecture",
        next_state="architecture_ready",
        next_stage="Designer",
        message="Architecture approved. Pipeline resuming at Designer.",
    ).to_dict()


@router.post("/architecture/revise")
def revise_architecture(
    project_id: str,
    body: ReviseRequest,
    workspace=Depends(get_workspace_manager),
    container=Depends(get_container),
) -> dict[str, Any]:
    """Request a revision. Stores feedback and re-runs Architect with it injected."""
    _assert_gate_state(project_id, "architecture", workspace)
    _store_gate_feedback(project_id, "architecture", body.feedback, container)
    workspace.update_state(project_id, ProjectState.ARCHITECTURE_READY)
    # Revert Architect from completed so it re-runs with feedback on next pipeline call
    _remove_from_completed(project_id, Stage.Architect.value, workspace)
    _schedule_resume(project_id, container)
    return GateResult(
        status="revision_requested",
        project_id=project_id,
        gate="architecture",
        next_state="architecture_ready",
        next_stage="Architect (revision)",
        message="Revision requested. Architect will re-run with your feedback.",
    ).to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Design gate
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/design/approve")
def approve_design(
    project_id: str,
    workspace=Depends(get_workspace_manager),
    container=Depends(get_container),
) -> dict[str, Any]:
    _assert_gate_state(project_id, "design", workspace)
    workspace.update_state(project_id, ProjectState.DESIGN_APPROVED)
    _schedule_resume(project_id, container)
    return GateResult(
        status="resumed",
        project_id=project_id,
        gate="design",
        next_state="design_approved",
        next_stage="Security",
        message="Design approved. Pipeline resuming at Security.",
    ).to_dict()


@router.post("/design/revise")
def revise_design(
    project_id: str,
    body: ReviseRequest,
    workspace=Depends(get_workspace_manager),
    container=Depends(get_container),
) -> dict[str, Any]:
    _assert_gate_state(project_id, "design", workspace)
    _store_gate_feedback(project_id, "design", body.feedback, container)
    workspace.update_state(project_id, ProjectState.DESIGN_APPROVED)
    _remove_from_completed(project_id, Stage.Designer.value, workspace)
    _schedule_resume(project_id, container)
    return GateResult(
        status="revision_requested",
        project_id=project_id,
        gate="design",
        next_state="design_approved",
        next_stage="Designer (revision)",
        message="Revision requested. Designer will re-run with your feedback.",
    ).to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Sprint plan gate
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/sprint-plan/approve")
def approve_sprint_plan(
    project_id: str,
    workspace=Depends(get_workspace_manager),
    container=Depends(get_container),
) -> dict[str, Any]:
    _assert_gate_state(project_id, "sprint_plan", workspace)
    workspace.update_state(project_id, ProjectState.SPRINT_PLAN_READY)
    _schedule_resume(project_id, container)
    return GateResult(
        status="resumed",
        project_id=project_id,
        gate="sprint_plan",
        next_state="sprint_plan_ready",
        next_stage="Sprint Execution",
        message="Sprint plan approved. Executing sprints.",
    ).to_dict()


@router.post("/sprint-plan/adjust")
def adjust_sprint_plan(
    project_id: str,
    body: AdjustRequest,
    workspace=Depends(get_workspace_manager),
    container=Depends(get_container),
) -> dict[str, Any]:
    """Re-run SprintPlanner with constraints (max_sprints and/or feedback)."""
    _assert_gate_state(project_id, "sprint_plan", workspace)
    feedback = body.feedback or ""
    if body.max_sprints is not None:
        feedback = f"Limit to {body.max_sprints} sprints maximum. " + feedback
    if feedback:
        _store_gate_feedback(project_id, "sprint_plan", feedback.strip(), container)
    workspace.update_state(project_id, ProjectState.SPRINT_PLAN_READY)
    _remove_from_completed(project_id, Stage.SprintPlanning.value, workspace)
    _schedule_resume(project_id, container)
    return GateResult(
        status="adjusted",
        project_id=project_id,
        gate="sprint_plan",
        next_state="sprint_plan_ready",
        next_stage="SprintPlanner (adjusted)",
        message="Adjustment requested. SprintPlanner will re-run with constraints.",
    ).to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _state_to_gate(state) -> str | None:
    for gate, gate_state in _GATE_STATES.items():
        if state == gate_state:
            return gate
    return None


def _assert_gate_state(project_id: str, gate: str, workspace) -> None:
    """Raise HTTP 409 if the project is not at the expected gate state."""
    expected = _GATE_STATES.get(gate)
    current = workspace.get_state(project_id)
    if current != expected:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Project {project_id} is not at gate '{gate}'. "
                f"Expected state '{expected.value if expected else gate}', got '{current.value if hasattr(current, 'value') else current}'."
            ),
        )


def _store_gate_feedback(project_id: str, gate: str, feedback: str, container) -> None:
    """Persist gate feedback to memory so the next stage run can inject it."""
    try:
        mm = container.resolve("memory_manager")
        mm.store(project_id, f"gate:feedback:{gate}", feedback)
        logger.info("gates: stored feedback for %s/%s (%d chars)", project_id, gate, len(feedback))
    except Exception as exc:
        logger.warning("gates: feedback storage failed for %s/%s: %s", project_id, gate, exc)


def _remove_from_completed(project_id: str, stage_value: str, workspace) -> None:
    """Remove a stage from stages_completed so the pipeline re-runs it."""
    try:
        data = workspace.load_project_json(project_id) or {}
        completed = [s for s in data.get("stages_completed", []) if s != stage_value]
        workspace.update_project_json(project_id, {"stages_completed": completed})
    except Exception as exc:
        logger.warning("gates: failed to remove %s from completed for %s: %s", stage_value, project_id, exc)


def _schedule_resume(project_id: str, container) -> None:
    """Fire-and-forget: schedule the pipeline to resume via background task.

    Currently runs synchronously on the API thread (acceptable for MVP —
    Phase 6 will move this to Celery). The pipeline is already idempotent
    so re-calling it is safe.
    """
    try:
        wm = container.resolve("workflow_manager")
        data = container.resolve("workspace_manager").load_project_json(project_id) or {}
        request = data.get("original_request") or data.get("description") or ""
        # run() is synchronous — for MVP this blocks the API response briefly.
        # TODO(Phase 6): replace with Celery pipeline_task.delay(project_id, request)
        import threading
        t = threading.Thread(
            target=_run_pipeline_safe,
            args=(wm, project_id, request),
            daemon=True,
        )
        t.start()
        logger.info("gates: pipeline resume scheduled for %s (background thread)", project_id)
    except Exception as exc:
        logger.warning("gates: failed to schedule pipeline resume for %s: %s", project_id, exc)


def _run_pipeline_safe(wm, project_id: str, request: str) -> None:
    """Run pipeline in background thread; catch and log all exceptions."""
    try:
        wm.run(project_id, request)
    except Exception as exc:
        logger.error("gates: background pipeline run failed for %s: %s", project_id, exc, exc_info=True)
