import logging
import threading
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from ..artifact.manager import ArtifactManager
from ..project.manager import ProjectManager
from ..shared.dto.stage_request import StageRequest
from ..shared.dto.workflow_request import WorkflowRequest
from ..shared.dto.workflow_result import WorkflowResult
from ..shared.enums.project_state import ProjectState
from ..shared.enums.stage import Stage
from ..workflow.dependency_graph import DependencyGraph
from ..workflow.manager import WorkflowManager
from ..workflow.stage_lookup import resolve_stage_name
from ..workspace.manager import WorkspaceManager
from .dependencies import get_artifact_manager, get_project_manager, get_workflow_manager, get_workspace_manager
from .middleware.jwt_auth import get_current_user
from ..tasks.pipeline_task import dispatch_pipeline
from ..shared.models.project import Project


def _assert_project_access(project: Project, user) -> None:
    """Raise 403 if the caller does not own the project and is not an admin."""
    if user.role == "admin":
        return
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access to this project is not permitted")

logger = logging.getLogger(__name__)

router = APIRouter()


def launch_pipeline_background(manager: WorkflowManager, project_id: str, req: str = "", skip_qa: bool = False, is_stage: bool = False, stage_name: str = "", comment_text: str = ""):
    """Launch pipeline execution in the background.

    For full pipeline runs (is_stage=False) delegates to dispatch_pipeline(),
    which uses Celery when CELERY_BROKER_URL is set and falls back to a daemon
    thread when Redis/Celery is unavailable.

    For stage-level runs (is_stage=True) uses a daemon thread directly — no
    Celery task exists for single-stage execution.

    Phase 6: threading.Thread for full pipeline runs replaced with dispatch_pipeline().
    """
    if is_stage:
        # Single-stage run — no Celery task for this path; keep threading.
        def _run_stage():
            try:
                manager.run_stage(project_id, stage_name, comment_text)
            except Exception as exc:
                logger.error(
                    "[workflow] stage pipeline crashed: project_id=%s stage=%s error=%s",
                    project_id, stage_name, exc,
                    exc_info=True,
                )
        threading.Thread(target=_run_stage, daemon=True, name=f"workflow-{project_id}").start()
    else:
        # Full pipeline run — Celery when available, thread fallback otherwise.
        dispatch_pipeline(manager, project_id, req, skip_qa)

class DesignApprovalRequest(BaseModel):
    feedback: str | None = None
    approved: bool = True
    modified_design: dict | None = None

@router.post("/workflow/start")
def start_workflow(
    request: WorkflowRequest,
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Run the complete multi-stage pipeline for request.project_id asynchronously."""
    project = project_manager.repository.load(request.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    content = request.request or f"Initialize project {request.project_id}"
    
    if manager.execution_state.is_running(request.project_id):
        state = manager.workspace_manager.get_state(request.project_id)
        return {
            "project_id": request.project_id,
            "state": state.value if hasattr(state, "value") else str(state),
            "success": True,
            "requires_user_action": False,
            "message": "Workflow is already running in background",
        }

    # Phase 6: replaced bare threading.Thread with dispatch_pipeline() so Celery
    # is used when CELERY_BROKER_URL is configured, with a thread fallback otherwise.
    dispatch_pipeline(manager, request.project_id, content)
    
    state = manager.workspace_manager.get_state(request.project_id)
    return {
        "project_id": request.project_id,
        "state": state.value if hasattr(state, "value") else str(state),
        "success": True,
        "requires_user_action": False,
        "action_needed": None,
        "completed_stages": [],
        "message": "Workflow pipeline started in background",
    }


@router.get("/workflow/{project_id}/design-review")
def get_design_review(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    artifact_manager: ArtifactManager = Depends(get_artifact_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Return the DesignArtifact formatted for UI preview rendering."""
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    state = workspace_manager.get_state(project_id)
    dr_data = workspace_state.get("design_review") or {}
    review_iteration = dr_data.get("iteration", 1)

    design_content = workspace_manager.load_approved_design(project_id)
    if not design_content:
        artifact = artifact_manager.get_artifact(project_id, Stage.Designer)
        if artifact and artifact.structured_content:
            design_content = artifact.structured_content
        elif artifact and artifact.content:
            from ..actions.base_action import BaseAction
            design_content = BaseAction.extract_json(artifact.content)

    if not design_content:
        from ..shared.schemas.design_schema import DesignArtifact
        design_content = DesignArtifact(project_id=project_id, project_name=workspace_state.get("name", "")).model_dump(mode="json")

    return {
        "project_id": project_id,
        "state": state.value if hasattr(state, "value") else str(state),
        "review_iteration": review_iteration,
        "design": design_content,
        "instructions": "Review the design above. Approve to begin coding, or provide specific feedback for changes.",
    }


@router.post("/workflow/{project_id}/design-review")
@router.post("/workflow/{project_id}/approve-design")
def post_design_review(
    project_id: str,
    request: DesignApprovalRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    artifact_manager: ArtifactManager = Depends(get_artifact_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Approve or request revision for the project design.

    On approval the pipeline auto-resumes as a background task so the user
    never has to manually call /continue after approving the design.
    On revision the pipeline pauses at DESIGN_READY; the user must call
    /continue (or the UI triggers it) to re-run the Designer with feedback.
    """
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if request.approved:
        if request.modified_design:
            workspace_manager.save_approved_design(project_id, request.modified_design)
            try:
                import json
                artifact_manager.save_artifact(
                    project_id=project_id,
                    stage=Stage.Designer,
                    content=json.dumps(request.modified_design, indent=2),
                    structured_content=request.modified_design,
                )
            except Exception as e:
                logger.warning(
                    "[post_design_review] Non-critical failure saving modified design artifact: %s",
                    str(e),
                    exc_info=True,
                )
        workspace_manager.update_design_review(project_id, "approved", request.feedback)
        workspace_manager.update_state(project_id, ProjectState.DESIGN_APPROVED)

        # Auto-resume: fire pipeline continuation as a background task so the
        # user does not need to call /continue manually after approval.
        if not manager.execution_state.is_running(project_id):
            original_req = (
                workspace_state.get("original_request")
                or workspace_state.get("description")
                or f"Project {project_id}"
            )
            launch_pipeline_background(manager, project_id, original_req)

        return {
            "state": "design_approved",
            "message": "Design approved — sprint planning starting",
            "next": "Sprint planning and coding will begin automatically",
        }
    else:
        workspace_manager.update_design_review(project_id, "revision_requested", request.feedback)
        workspace_manager.update_state(project_id, ProjectState.DESIGN_READY)
        updated_data = workspace_manager.load_project_json(project_id) or {}
        new_iteration = updated_data.get("design_review", {}).get("iteration", 2)

        # Auto-resume for revision: re-run the Designer immediately with the new feedback.
        if not manager.execution_state.is_running(project_id):
            original_req = (
                workspace_state.get("original_request")
                or workspace_state.get("description")
                or f"Project {project_id}"
            )
            launch_pipeline_background(manager, project_id, original_req)

        return {
            "state": "design_revision",
            "iteration": new_iteration,
            "message": "Design revision requested — regenerating design with your feedback.",
        }


@router.post("/workflow/{project_id}/continue")
def continue_workflow(
    project_id: str,
    manager: WorkflowManager = Depends(get_workflow_manager),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Resume pipeline from current state asynchronously."""
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    original_request = (
        workspace_state.get("original_request")
        or workspace_state.get("description")
        or f"Resume project {project_id}"
    )

    if manager.execution_state.is_running(project_id):
        state = workspace_manager.get_state(project_id)
        return {
            "project_id": project_id,
            "state": state.value if hasattr(state, "value") else str(state),
            "success": True,
            "message": "Workflow is already running in background",
        }

    launch_pipeline_background(manager, project_id, original_request)
    state = workspace_manager.get_state(project_id)
    return {
        "project_id": project_id,
        "state": state.value if hasattr(state, "value") else str(state),
        "success": True,
        "requires_user_action": False,
        "action_needed": None,
        "message": "Workflow pipeline resumed in background",
    }


@router.get("/workflow/{project_id}/status")
@router.get("/workflow/{project_id}")
def workflow_status(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Report project_id's status and state machine progress."""
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    state = workspace_manager.get_state(project_id)
    completed_stages = list(workspace_state.get("stages_completed", []))
    failed_stage = workspace_state.get("failed_at_stage") or workspace_state.get("failed_stage")
    was_stopped = bool(workspace_state.get("stopped"))

    # ── Stage inflation ───────────────────────────────────────────────────────
    # _sanitize_stages_completed strips non-STAGE_ORDER stages (DomainResearch,
    # Clarifying, ScrumMaster, FileStructurePlanner, BackendDeveloper,
    # FrontendDeveloper, SprintDeploy, SprintReview).  Re-add them here so the
    # frontend's 20-stage STAGES array can correctly highlight each circle.
    _PRE_PIPELINE = ["DomainResearch", "Clarifying"]
    _SPRINT_SUB = [
        "ScrumMaster", "FileStructurePlanner", "BackendDeveloper",
        "FrontendDeveloper", "SprintDeploy", "SprintReview",
    ]
    # States where all sprint-execution sub-stages have definitively completed.
    _POST_SPRINT_STATES = frozenset({
        "all_sprints_complete", "qa_complete", "deployable", "done",
        "resuming_from_change",
    })

    state_str = state.value if hasattr(state, "value") else str(state)
    inflated = list(completed_stages)

    # DomainResearch + Clarifying precede every state past empty/not_started.
    if state_str not in ("", "empty", "not_started"):
        for s in _PRE_PIPELINE:
            if s not in inflated:
                inflated.append(s)

    # Sprint execution sub-stages are guaranteed once all sprints are complete.
    if state_str in _POST_SPRINT_STATES:
        for s in _SPRINT_SUB:
            if s not in inflated:
                inflated.append(s)

    # ── Progress ──────────────────────────────────────────────────────────────
    # 21 total stages: 13 in STAGE_ORDER (workflow.json, incl. clarification)
    # + 8 non-STAGE_ORDER sprint-internal stages.
    FULL_PIPELINE_STAGE_COUNT = 21
    total_stages = FULL_PIPELINE_STAGE_COUNT
    if state_str in ("deployable", "done"):
        progress_percent = 100
    else:
        progress_percent = round(100 * len(inflated) / total_stages) if total_stages else 0

    current_sprint = workspace_state.get("current_sprint_number", 0)
    total_sprints = workspace_state.get("total_sprints", 0)
    curr_sprint_dict = workspace_state.get("current_sprint") or {}
    sprint_name = curr_sprint_dict.get("name") or (f"Sprint {current_sprint}" if current_sprint else "No active sprint")

    completed_sprints = workspace_state.get("completed_sprints", [])
    sprint_progress = f"{len(completed_sprints)}/{total_sprints} sprints complete"
    remaining_sprints = max(0, total_sprints - len(completed_sprints))
    estimated_completion = f"{remaining_sprints} sprints remaining"

    is_running = manager.execution_state.is_running(project_id)
    if is_running:
        status_str = "running"
    elif state == ProjectState.FAILED:
        status_str = "failed"
    elif state == ProjectState.EMPTY:
        status_str = "not_started"
    elif state in [ProjectState.DEPLOYABLE, ProjectState.DONE]:
        status_str = "complete"
    elif was_stopped:
        status_str = "stopped"
    else:
        status_str = "paused"

    # clarifying/paused = pipeline kicked off but LLM timed out before generating Q&A.
    # Treat it as needing user action so the frontend shows the Continue prompt.
    requires_action = state in [
        ProjectState.DESIGN_REVIEW_PENDING, ProjectState.QA_PENDING
    ]

    data = {
        "project_id": project_id,
        "state": state.value if hasattr(state, "value") else str(state),
        "status": status_str,
        "requires_user_action": requires_action,
        "current_sprint": current_sprint,
        "total_sprints": total_sprints,
        "sprint_name": sprint_name,
        "sprint_progress": sprint_progress,
        "estimated_completion": estimated_completion,
        "current_stage": workspace_state.get("current_stage"),
        "completed_stages": inflated,
        "failed_stage": failed_stage,
        "total_stages": total_stages,
        "progress_percent": progress_percent,
    }

    if data["state"] == "clarifying" or status_str == "paused":
        qa = workspace_manager.get_qa_session(project_id)
        if qa and "questions" in qa:
            data["clarification_questions"] = [
                q.get("question") for q in qa["questions"] if "question" in q
            ]

    return data


class QAAnswerRequest(BaseModel):
    question_index: int
    answer: str


class QASkipRequest(BaseModel):
    question_index: int


@router.get("/workflow/{project_id}/qa")
def get_qa_session(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    qa = workspace_manager.get_qa_session(project_id)
    questions = qa.get("questions", [])
    answers = qa.get("answers", [])
    total_questions = len(questions)
    answered_count = len(answers)

    current_q_index = qa.get("current_question_index", 0)
    current_q = None
    if current_q_index < total_questions:
        current_q = questions[current_q_index]

    previous_answers = []
    for a in answers:
        q_idx = a.get("question_index", 0)
        q_text = questions[q_idx].get("question", "") if q_idx < len(questions) else ""
        previous_answers.append({
            "question_index": q_idx,
            "question": q_text,
            "answer": a.get("answer", ""),
        })

    return {
        "project_id": project_id,
        "status": qa.get("status", "pending"),
        "total_questions": total_questions,
        "answered": answered_count,
        "current_question_index": current_q_index,
        "current_question": current_q,
        "previous_answers": previous_answers,
        "questions": questions,
        "is_complete": answered_count >= total_questions and total_questions > 0,
    }


@router.post("/workflow/{project_id}/qa/answer")
def answer_qa_question(
    project_id: str,
    req: QAAnswerRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_manager.save_qa_answer(project_id, req.question_index, req.answer)
    qa = workspace_manager.get_qa_session(project_id)
    total_questions = qa.get("total_questions", 0)
    answered_count = qa.get("answered", 0)
    is_complete = answered_count >= total_questions and total_questions > 0

    next_q = None
    current_q_index = qa.get("current_question_index", 0)
    questions = qa.get("questions", [])
    if current_q_index < total_questions:
        next_q = questions[current_q_index]

    return {
        "saved": True,
        "next_question": next_q,
        "progress": {"answered": answered_count, "total": total_questions},
        "is_complete": is_complete,
    }


@router.post("/workflow/{project_id}/qa/skip")
def skip_qa_question(
    project_id: str,
    req: QASkipRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    qa = workspace_manager.get_qa_session(project_id)
    questions = qa.get("questions", [])
    if req.question_index < len(questions):
        q = questions[req.question_index]
        if q.get("priority") == "CRITICAL":
            raise HTTPException(status_code=400, detail="CRITICAL questions cannot be skipped.")

    workspace_manager.skip_qa_question(project_id, req.question_index)
    updated_qa = workspace_manager.get_qa_session(project_id)
    total_questions = updated_qa.get("total_questions", 0)
    answered_count = updated_qa.get("answered", 0)
    is_complete = answered_count >= total_questions and total_questions > 0

    return {
        "skipped": True,
        "progress": {"answered": answered_count, "total": total_questions},
        "is_complete": is_complete,
    }


@router.post("/workflow/{project_id}/qa/complete")
def complete_qa_session(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    # FIX-C: Guard against duplicate starts. If the pipeline is already running
    # (e.g. the frontend re-mounts QAPanel and calls qa/complete again), return
    # the current state instead of enqueuing another background task and
    # overwriting the state back to QA_IN_PROGRESS.
    if manager.execution_state.is_running(project_id):
        state = workspace_manager.get_state(project_id)
        return {
            "status": "running",
            "state": state.value if hasattr(state, "value") else str(state),
            "message": "Pipeline is already running",
        }

    workspace_manager.update_state(project_id, ProjectState.QA_IN_PROGRESS)
    original_req = (
        workspace_state.get("original_request")
        or workspace_state.get("description")
        or f"Project {project_id}"
    )
    launch_pipeline_background(manager, project_id, original_req)
    return {
        "status": "processing",
        "message": "Processing your answers...",
    }



@router.post("/workflow/{project_id}/stop")
def stop_workflow(
    project_id: str,
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Flag project_id's in-flight pipeline/stage run to stop at its next checkpoint."""
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    stopped = manager.execution_state.request_stop(project_id)
    return {"project_id": project_id, "stop_requested": stopped}


class HumanApprovalRequest(BaseModel):
    stage: str | None = None
    approved: bool = True
    comment: str | None = None


@router.get("/workflow/{project_id}/pending-approval")
def get_pending_approval(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    artifact_manager: ArtifactManager = Depends(get_artifact_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    state = workspace_manager.get_state(project_id)
    curr_stage = workspace_state.get("current_stage") or "architect"
    st_val = state.value if hasattr(state, "value") else str(state)
    awaiting = (state == ProjectState.AWAITING_HUMAN_APPROVAL) or (st_val in ["awaiting_human_approval", "awaiting_human", "human_action_required"])

    artifact_preview = ""
    reviewer_decision = {"approved": True, "findings": []}

    try:
        for s in Stage:
            if s.value.lower() == curr_stage.lower():
                art = artifact_manager.get_artifact(project_id, s)
                if art and art.content:
                    artifact_preview = art.content[:500]
                break
    except Exception as _preview_exc:
        logger.warning(
            "workflow: could not load artifact preview for project %s stage %s: %s",
            project_id,
            curr_stage,
            _preview_exc,
            exc_info=True,
        )

    return {
        "stage": curr_stage,
        "artifact_preview": artifact_preview,
        "reviewer_decision": reviewer_decision,
        "awaiting_human": awaiting,
    }


@router.post("/workflow/{project_id}/approve")
def approve_human_stage(
    project_id: str,
    req: HumanApprovalRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if req.approved:
        workspace_state_dict = workspace_manager.load_project_json(project_id) or {}
        orig_req = workspace_state_dict.get("original_request") or workspace_state_dict.get("description") or f"Project {project_id}"
        launch_pipeline_background(manager, project_id, orig_req)
        return {"project_id": project_id, "approved": True, "message": "Stage approved, pipeline continuing"}
    else:
        stage_name = req.stage or workspace_state.get("current_stage") or "architect"
        comment_text = req.comment or "Operator requested changes"
        launch_pipeline_background(manager, project_id, is_stage=True, stage_name=stage_name, comment_text=comment_text)
        return {"project_id": project_id, "approved": False, "message": f"Stage {stage_name} rejected, retrying with feedback"}


@router.post("/workflow/stage", response_model=WorkflowResult)
def run_single_stage(
    request: StageRequest,
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> WorkflowResult:
    """Run exactly one named stage (for debugging)."""
    project = project_manager.repository.load(request.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    stage_name = resolve_stage_name(request.stage)
    return manager.run_stage(request.project_id, stage_name, request.request)


class RequirementChangeRequest(BaseModel):
    description: str


class ChangeConfirmRequest(BaseModel):
    change_id: str
    confirmed: bool = True
    comment: str | None = ""


class ChangeCancelRequest(BaseModel):
    change_id: str


@router.post("/workflow/{project_id}/change")
def submit_requirement_change(
    project_id: str,
    req: RequirementChangeRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    analysis = manager.submit_requirement_change(project_id, req.description)
    if hasattr(analysis, "model_dump"):
        return analysis.model_dump(mode="json")
    return dict(analysis)


@router.post("/workflow/{project_id}/change/confirm")
def confirm_requirement_change(
    project_id: str,
    req: ChangeConfirmRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return manager.apply_requirement_change(
        project_id=project_id,
        change_id=req.change_id,
        confirmed=req.confirmed,
        user_comment=req.comment or "",
    )


@router.post("/workflow/{project_id}/change/cancel")
def cancel_requirement_change(
    project_id: str,
    req: ChangeCancelRequest,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return manager.apply_requirement_change(
        project_id=project_id,
        change_id=req.change_id,
        confirmed=False,
    )


@router.get("/workflow/{project_id}/design-preview")
def get_design_preview(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    artifact_manager: ArtifactManager = Depends(get_artifact_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Return a self-contained HTML mockup generated from the DesignArtifact JSON.

    Extracts page layouts, component specs, and design tokens from the stored
    DesignArtifact and renders them as a static HTML wireframe the frontend can
    display in an iframe — no external requests, no JS required.
    """
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)

    design_content: dict = {}
    design_content_raw = workspace_manager.load_approved_design(project_id)
    if not design_content_raw:
        artifact = artifact_manager.get_artifact(project_id, Stage.Designer)
        if artifact and artifact.structured_content:
            design_content = artifact.structured_content
        elif artifact and artifact.content:
            from ..actions.base_action import BaseAction
            design_content = BaseAction.extract_json(artifact.content) or {}
    else:
        design_content = design_content_raw if isinstance(design_content_raw, dict) else {}

    html = _build_design_preview_html(project.name, design_content)
    return {"html": html}


def _build_design_preview_html(project_name: str, design: dict) -> str:
    """Generate a self-contained HTML wireframe from DesignArtifact fields."""
    # Extract design tokens
    design_system = design.get("design_system") or {}
    colors = design_system.get("colors") or {}
    primary_color = colors.get("primary", "#6366f1")
    bg_color = colors.get("background", "#0f0f0f")
    text_color = colors.get("text_primary", "#e9e9ed")
    surface_color = colors.get("surface", "#1a1a1a")
    border_color = "#2a2a2a"

    pages = design.get("page_layouts") or design.get("pages") or []
    components = design.get("components") or []
    user_flows = design.get("user_flows") or []

    def page_card(page: dict) -> str:
        name = page.get("name") or page.get("page_id") or "Page"
        route = page.get("route") or ""
        desc = page.get("description") or page.get("layout") or ""
        comps = page.get("components") or []
        comps_html = ""
        if comps:
            comps_html = "<div style='margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;'>" + "".join(
                f"<span style='font-size:10px;padding:2px 8px;background:rgba(99,102,241,.15);border:1px solid rgba(99,102,241,.3);border-radius:100px;color:{primary_color};'>{c}</span>"
                for c in (comps[:8] if isinstance(comps, list) else [])
            ) + "</div>"
        return f"""<div style='background:{surface_color};border:1px solid {border_color};border-radius:10px;padding:14px 16px;'>
  <div style='font-size:13px;font-weight:600;color:{text_color};margin-bottom:4px;'>{name}</div>
  {f"<div style='font-size:11px;color:#666;font-family:monospace;margin-bottom:4px;'>{route}</div>" if route else ""}
  {f"<div style='font-size:12px;color:#888;line-height:1.4;'>{desc}</div>" if desc else ""}
  {comps_html}
</div>"""

    def component_card(comp: dict) -> str:
        name = comp.get("name") or comp.get("component_id") or "Component"
        shadcn = comp.get("shadcn_component") or ""
        desc = comp.get("description") or comp.get("purpose") or ""
        return f"""<div style='background:{surface_color};border:1px solid {border_color};border-radius:8px;padding:12px 14px;'>
  <div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>
    <span style='font-size:12px;font-weight:600;color:{text_color};'>{name}</span>
    {f"<span style='font-size:10px;padding:1px 7px;background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.25);border-radius:100px;color:#10b981;'>{shadcn}</span>" if shadcn else ""}
  </div>
  {f"<div style='font-size:11px;color:#888;line-height:1.4;'>{desc}</div>" if desc else ""}
</div>"""

    def flow_item(flow: dict) -> str:
        name = flow.get("name") or flow.get("flow_id") or "Flow"
        entry = flow.get("entry_point") or ""
        steps = flow.get("steps") or []
        steps_html = ""
        if steps:
            step_items = []
            for s in (steps[:5] if isinstance(steps, list) else []):
                if isinstance(s, dict):
                    step_items.append(f"<li style='font-size:11px;color:#888;'>{s.get('action','')}</li>")
                else:
                    step_items.append(f"<li style='font-size:11px;color:#888;'>{s}</li>")
            steps_html = f"<ol style='margin:6px 0 0 16px;padding:0;display:flex;flex-direction:column;gap:3px;'>{''.join(step_items)}</ol>"
        return f"""<div style='padding:10px 14px;border-bottom:1px solid {border_color};'>
  <div style='font-size:12px;font-weight:600;color:{text_color};margin-bottom:2px;'>{name}</div>
  {f"<div style='font-size:11px;color:#666;'>Entry: {entry}</div>" if entry else ""}
  {steps_html}
</div>"""

    pages_section = ""
    if pages:
        cards = "\n".join(page_card(p) if isinstance(p, dict) else "" for p in pages[:12])
        pages_section = f"""<section>
  <h2 style='font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#555;margin:0 0 12px;'>Pages ({len(pages)})</h2>
  <div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px;'>{cards}</div>
</section>"""

    components_section = ""
    if components:
        cards = "\n".join(component_card(c) if isinstance(c, dict) else "" for c in components[:20])
        components_section = f"""<section>
  <h2 style='font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#555;margin:0 0 12px;'>Components ({len(components)})</h2>
  <div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;'>{cards}</div>
</section>"""

    flows_section = ""
    if user_flows:
        items = "\n".join(flow_item(f) if isinstance(f, dict) else "" for f in user_flows[:8])
        flows_section = f"""<section>
  <h2 style='font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:#555;margin:0 0 12px;'>User Flows ({len(user_flows)})</h2>
  <div style='background:{surface_color};border:1px solid {border_color};border-radius:10px;overflow:hidden;'>{items}</div>
</section>"""

    empty = ""
    if not pages and not components and not user_flows:
        empty = f"<div style='text-align:center;padding:60px 20px;color:#555;'>No design data available yet.</div>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{project_name} — Design Preview</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;background:{bg_color};color:{text_color};padding:24px;}}
</style>
</head>
<body>
<header style='margin-bottom:28px;'>
  <h1 style='font-size:20px;font-weight:700;color:{text_color};margin-bottom:4px;'>{project_name}</h1>
  <p style='font-size:12px;color:#555;'>Design preview — auto-generated from DesignArtifact</p>
</header>
<div style='display:flex;flex-direction:column;gap:28px;'>
{pages_section}
{components_section}
{flows_section}
{empty}
</div>
</body>
</html>"""


@router.get("/workflow/{project_id}/changes")
def list_requirement_changes(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    changes = workspace_state.get("requirement_changes", [])
    return {
        "project_id": project_id,
        "changes": changes,
    }

