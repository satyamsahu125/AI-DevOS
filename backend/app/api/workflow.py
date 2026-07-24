from fastapi import APIRouter, Depends, HTTPException

from ..project.manager import ProjectManager
from ..shared.dto.stage_request import StageRequest
from ..shared.dto.workflow_request import WorkflowRequest
from ..shared.dto.workflow_result import WorkflowResult
from ..workflow.dependency_graph import DependencyGraph
from ..workflow.manager import WorkflowManager
from ..workflow.stage_lookup import resolve_stage_name
from ..workspace.manager import WorkspaceManager
from .dependencies import get_project_manager, get_workflow_manager, get_workspace_manager

router = APIRouter()


@router.post("/workflow/start")
def start_workflow(
    request: WorkflowRequest,
    manager: WorkflowManager = Depends(get_workflow_manager),
    project_manager: ProjectManager = Depends(get_project_manager),
) -> dict:
    """Run the complete multi-stage pipeline for request.project_id, using request.request as the original task."""
    if not project_manager.repository.exists(request.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    content = request.request or f"Initialize project {request.project_id}"
    result = manager.run(request.project_id, content)
    return {
        "project_id": result.project_id,
        "success": result.success,
        "completed_stages": result.completed_stages,
        "failed_stage": result.failed_stage,
        "message": result.message,
    }


@router.get("/workflow/{project_id}")
def workflow_status(
    project_id: str,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    manager: WorkflowManager = Depends(get_workflow_manager),
) -> dict:
    """Report project_id's real pipeline progress, read from its workspace project.json (404 if never initialized).

    "running" means a stage is genuinely executing in this process right now (see
    ExecutionStateRegistry) -- not just "fewer stages are done than total". A project that's
    partway through the pipeline but has nothing actually in flight (e.g. after a backend
    restart, or simply not yet resumed) reports "paused", so the UI never shows a live spinner
    for work that isn't actually happening.
    """
    workspace_state = workspace_manager.load_project_json(project_id)
    if workspace_state is None:
        raise HTTPException(status_code=404, detail="Project not found")

    completed_stages = list(workspace_state.get("stages_completed", []))
    failed_stage = workspace_state.get("failed_stage")
    was_stopped = bool(workspace_state.get("stopped"))
    total_stages = len(DependencyGraph.STAGE_ORDER)
    progress_percent = round(100 * len(completed_stages) / total_stages) if total_stages else 0
    is_running = manager.execution_state.is_running(project_id)

    if is_running:
        status = "running"
    elif failed_stage:
        status = "failed"
    elif not completed_stages:
        status = "not_started"
    elif len(completed_stages) >= total_stages:
        status = "complete"
    elif was_stopped:
        status = "stopped"
    else:
        status = "paused"

    return {
        "project_id": project_id,
        "current_stage": workspace_state.get("current_stage"),
        "completed_stages": completed_stages,
        "failed_stage": failed_stage,
        "total_stages": total_stages,
        "progress_percent": progress_percent,
        "status": status,
    }


@router.post("/workflow/{project_id}/stop")
def stop_workflow(project_id: str, manager: WorkflowManager = Depends(get_workflow_manager)) -> dict:
    """Flag project_id's in-flight pipeline/stage run to stop at its next checkpoint (between
    retry attempts, or between stages) -- it cannot interrupt a single LLM call already in
    flight, since that's a blocking HTTP request to the model provider."""
    stopped = manager.execution_state.request_stop(project_id)
    return {"project_id": project_id, "stop_requested": stopped}


@router.post("/workflow/stage", response_model=WorkflowResult)
def run_single_stage(request: StageRequest, manager: WorkflowManager = Depends(get_workflow_manager)) -> WorkflowResult:
    """Run exactly one named stage (for debugging) -- accepts either "ProductOwner" or "product_owner" form."""
    stage_name = resolve_stage_name(request.stage)
    return manager.run_stage(request.project_id, stage_name, request.request)
