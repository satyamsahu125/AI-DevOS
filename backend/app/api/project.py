from fastapi import APIRouter, Depends

from ..project.manager import ProjectManager
from ..shared.dto.project_request import ProjectRequest
from ..shared.dto.project_response import ProjectResponse
from .dependencies import get_project_manager

router = APIRouter()


@router.post("/projects", response_model=ProjectResponse)
def create_project(request: ProjectRequest, manager: ProjectManager = Depends(get_project_manager)) -> ProjectResponse:
    return manager.create_project(request)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, manager: ProjectManager = Depends(get_project_manager)) -> ProjectResponse:
    project = manager.repository.load(project_id)
    if project is None:
        raise ValueError("project not found")
    return ProjectResponse(project=project, success=True, message="project loaded")
