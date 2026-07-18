from fastapi import APIRouter, Depends

from ..shared.dto.workflow_request import WorkflowRequest
from ..shared.dto.workflow_result import WorkflowResult
from ..workflow.manager import WorkflowManager
from .dependencies import get_workflow_manager

router = APIRouter()


@router.post("/workflow/start", response_model=WorkflowResult)
def start_workflow(request: WorkflowRequest, manager: WorkflowManager = Depends(get_workflow_manager)) -> WorkflowResult:
    return manager.run_stage("ProductOwner", request.project_id)


@router.get("/workflow/{project_id}", response_model=WorkflowResult)
def workflow_status(project_id: str, manager: WorkflowManager = Depends(get_workflow_manager)) -> WorkflowResult:
    return WorkflowResult(workflow=None, success=True, message="workflow status")
