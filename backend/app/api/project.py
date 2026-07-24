from fastapi import APIRouter, Depends, HTTPException, Response

from ..artifact.manager import ArtifactManager
from ..memory.manager import MemoryManager
from ..project.manager import ProjectManager
from ..shared.dto.project_request import ProjectRequest
from ..shared.dto.project_response import ProjectResponse
from ..workspace.manager import WorkspaceManager
from .dependencies import get_artifact_manager, get_memory_manager, get_project_manager, get_workspace_manager

router = APIRouter()


@router.post("/projects", response_model=ProjectResponse)
def create_project(request: ProjectRequest, manager: ProjectManager = Depends(get_project_manager)) -> ProjectResponse:
    return manager.create_project(request)


@router.get("/projects")
def list_projects(manager: ProjectManager = Depends(get_project_manager)) -> list[dict]:
    """Return a summary of every known project."""
    return [
        {
            "project_id": project.project_id,
            "name": project.name,
            "status": project.status,
            "current_stage": project.current_stage.value,
            "created_at": project.created_at.isoformat(),
        }
        for project in manager.repository.list_projects()
    ]


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    manager: ProjectManager = Depends(get_project_manager),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    artifact_manager: ArtifactManager = Depends(get_artifact_manager),
) -> dict:
    """Return the project's static record merged with its live workspace progress and approved artifacts."""
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_state = workspace_manager.load_project_json(project_id) or {}
    artifacts = [
        {
            "stage": artifact.name,
            "file": str(artifact.location) if artifact.location else "",
            "json": str(workspace_manager.get_workspace_path(project_id) / "artifacts" / f"{artifact.name}.json"),
            "created_at": project.created_at.isoformat(),
            "attempt": artifact.attempt,
        }
        for artifact in artifact_manager.list_artifacts(project_id)
    ]

    return {
        "project_id": project.project_id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "current_stage": workspace_state.get("current_stage", project.current_stage.value),
        "stages_completed": workspace_state.get("stages_completed", []),
        "artifacts": artifacts,
        "workspace_path": project.workspace_path,
    }


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    manager: ProjectManager = Depends(get_project_manager),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    artifact_manager: ArtifactManager = Depends(get_artifact_manager),
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> Response:
    """Delete project_id's workspace, project record, artifact rows, and namespaced memory records."""
    if not manager.repository.exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    workspace_manager.delete_workspace(project_id)
    manager.repository.delete(project_id)
    artifact_manager.delete_project_artifacts(project_id)
    memory_manager.delete_project(project_id)
    return Response(status_code=204)
