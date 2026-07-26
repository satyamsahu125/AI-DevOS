import logging
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

logger = logging.getLogger(__name__)

router = APIRouter()


class DesignApprovalRequest(BaseModel):
    feedback: str | None = None
    approved: bool = True
    modified_design: dict | None = None


@router.post("/workflow/start")
def start_workflow(
    request: WorkflowRequest,
    background_tasks: BackgroundTasks,
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> dict:
    """Run the complete multi-stage pipeline for request.project_id asynchronously."""
    if not project_manager.repository.exists(request.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
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

    background_tasks.add_task(manager.run, request.project_id, content)
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
) -> dict:
    """Return the DesignArtifact formatted for UI preview rendering."""
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
    background_tasks: BackgroundTasks,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    artifact_manager: ArtifactManager = Depends(get_artifact_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
) -> dict:
    """Approve or request revision for the project design.

    On approval the pipeline auto-resumes as a background task so the user
    never has to manually call /continue after approving the design.
    On revision the pipeline pauses at DESIGN_READY; the user must call
    /continue (or the UI triggers it) to re-run the Designer with feedback.
    """
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
            background_tasks.add_task(manager.run, project_id, original_req)

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
            background_tasks.add_task(manager.run, project_id, original_req)

        return {
            "state": "design_revision",
            "iteration": new_iteration,
            "message": "Design revision requested — regenerating design with your feedback.",
        }


@router.post("/workflow/{project_id}/continue")
def continue_workflow(
    project_id: str,
    background_tasks: BackgroundTasks,
    manager: WorkflowManager = Depends(get_workflow_manager),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
) -> dict:
    """Resume pipeline from current state asynchronously."""
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

    background_tasks.add_task(manager.run, project_id, original_request)
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
) -> dict:
    """Report project_id's status and state machine progress."""
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    state = workspace_manager.get_state(project_id)
    completed_stages = list(workspace_state.get("stages_completed", []))
    failed_stage = workspace_state.get("failed_at_stage") or workspace_state.get("failed_stage")
    was_stopped = bool(workspace_state.get("stopped"))
    total_stages = len(DependencyGraph.STAGE_ORDER)
    progress_percent = round(100 * len(completed_stages) / total_stages) if total_stages else 0

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

    requires_action = state in [ProjectState.DESIGN_REVIEW_PENDING, ProjectState.QA_PENDING, ProjectState.QA_IN_PROGRESS]

    return {
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
        "completed_stages": completed_stages,
        "failed_stage": failed_stage,
        "total_stages": total_stages,
        "progress_percent": progress_percent,
    }


class QAAnswerRequest(BaseModel):
    question_index: int
    answer: str


class QASkipRequest(BaseModel):
    question_index: int


@router.get("/workflow/{project_id}/qa")
def get_qa_session(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
) -> dict:
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
) -> dict:
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
) -> dict:
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
    background_tasks: BackgroundTasks,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
) -> dict:
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
    background_tasks.add_task(manager.run, project_id, original_req)
    return {
        "status": "processing",
        "message": "Processing your answers...",
    }



@router.post("/workflow/{project_id}/stop")
def stop_workflow(project_id: str, manager: WorkflowManager = Depends(get_workflow_manager)) -> dict:
    """Flag project_id's in-flight pipeline/stage run to stop at its next checkpoint."""
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
) -> dict:
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
    except Exception:
        pass

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
    background_tasks: BackgroundTasks,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
) -> dict:
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    if req.approved:
        workspace_state_dict = workspace_manager.load_project_json(project_id) or {}
        orig_req = workspace_state_dict.get("original_request") or workspace_state_dict.get("description") or f"Project {project_id}"
        background_tasks.add_task(manager.run, project_id, orig_req)
        return {"project_id": project_id, "approved": True, "message": "Stage approved, pipeline continuing"}
    else:
        stage_name = req.stage or workspace_state.get("current_stage") or "architect"
        comment_text = req.comment or "Operator requested changes"
        background_tasks.add_task(manager.run_stage, project_id, stage_name, comment_text)
        return {"project_id": project_id, "approved": False, "message": f"Stage {stage_name} rejected, retrying with feedback"}


@router.post("/workflow/stage", response_model=WorkflowResult)
def run_single_stage(request: StageRequest, manager: WorkflowManager = Depends(get_workflow_manager)) -> WorkflowResult:
    """Run exactly one named stage (for debugging)."""
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
) -> dict:
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
) -> dict:
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
) -> dict:
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return manager.apply_requirement_change(
        project_id=project_id,
        change_id=req.change_id,
        confirmed=False,
    )


@router.get("/workflow/{project_id}/changes")
def list_requirement_changes(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
) -> dict:
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    changes = workspace_state.get("requirement_changes", [])
    return {
        "project_id": project_id,
        "changes": changes,
    }

