from fastapi import APIRouter, Depends, HTTPException, Response

from ..artifact.manager import ArtifactManager
from ..memory.manager import MemoryManager
from ..project.manager import ProjectManager
from ..shared.dto.project_request import ProjectRequest
from ..shared.dto.project_response import ProjectResponse
from ..workspace.manager import WorkspaceManager
from ..workspace.project_files import ProjectFileManager
from .dependencies import (
    get_artifact_manager,
    get_memory_manager,
    get_project_file_manager,
    get_project_manager,
    get_workspace_manager,
)

router = APIRouter()


@router.post("/projects", response_model=ProjectResponse, status_code=201)
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


@router.get("/projects/{project_id}/files")
def list_project_files(
    project_id: str,
    project_file_manager: ProjectFileManager = Depends(get_project_file_manager),
) -> dict:
    """Lists all real generated files in project/ directory."""
    project_dir = project_file_manager.project_root(project_id)
    backend_files = project_file_manager.list_written(project_id, "backend")
    frontend_files = project_file_manager.list_written(project_id, "frontend")

    file_list = []
    if project_dir.exists():
        for p in project_dir.rglob("*"):
            if p.is_file() and ".attempt-" not in p.name:
                rel_path = str(p.relative_to(project_dir)).replace("\\", "/")
                ext = p.suffix.lower()
                lang_map = {
                    ".py": "python",
                    ".ts": "typescript",
                    ".tsx": "typescript",
                    ".js": "javascript",
                    ".jsx": "javascript",
                    ".yaml": "yaml",
                    ".yml": "yaml",
                    ".json": "json",
                    ".md": "markdown",
                    ".html": "html",
                    ".css": "css",
                }
                file_list.append({
                    "path": rel_path,
                    "size_bytes": p.stat().st_size,
                    "language": lang_map.get(ext, ext.lstrip(".")),
                    "sprint": 1,
                })

    return {
        "project_id": project_id,
        "project_path": str(project_dir),
        "total_files": len(file_list),
        "files": file_list,
        "backend": backend_files,
        "frontend": frontend_files,
    }


@router.get("/projects/{project_id}/files/{file_path:path}")
def get_project_file_content(
    project_id: str,
    file_path: str,
    project_file_manager: ProjectFileManager = Depends(get_project_file_manager),
) -> dict:
    """Returns actual content of a generated file."""
    if ".." in file_path:
        raise HTTPException(status_code=400, detail="Path traversal rejected")

    project_dir = project_file_manager.project_root(project_id)
    full_path = project_dir / file_path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    content = full_path.read_text(encoding="utf-8")
    ext = full_path.suffix.lower()
    lang_map = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".md": "markdown",
        ".html": "html",
        ".css": "css",
    }
    return {
        "content": content,
        "language": lang_map.get(ext, ext.lstrip(".")),
        "size": len(content),
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
