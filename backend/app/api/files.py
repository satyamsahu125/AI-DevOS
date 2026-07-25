import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Response

from ..project.manager import ProjectManager
from ..workspace.project_files import ProjectFileManager
from ..workspace.project_readme import build_run_instructions
from .dependencies import get_project_file_manager, get_project_manager, get_workspace_manager
from ..workspace.manager import WorkspaceManager

router = APIRouter()


@router.get("/projects/{project_id}/files")
def list_project_files(project_id: str, project_file_manager: ProjectFileManager = Depends(get_project_file_manager)) -> dict:
    """Return the real generated project's file tree (paths only), split by area."""
    return {
        "backend": project_file_manager.list_written(project_id, "backend"),
        "frontend": project_file_manager.list_written(project_id, "frontend"),
    }


@router.get("/projects/{project_id}/files/{area}/{file_path:path}")
def get_project_file_content(
    project_id: str, area: str, file_path: str, project_file_manager: ProjectFileManager = Depends(get_project_file_manager),
) -> dict:
    """Return one real generated file's content. 404 if it doesn't exist or escapes the project area."""
    area_root = project_file_manager.area_dir(project_id, area).resolve()
    target = (area_root / file_path).resolve()
    if area_root not in target.parents and target != area_root:
        raise HTTPException(status_code=400, detail="Invalid file path")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "project_id": project_id,
        "area": area,
        "path": file_path,
        "content": target.read_text(encoding="utf-8"),
    }


@router.get("/projects/{project_id}/run-instructions")
def get_run_instructions(
    project_id: str,
    project_manager: ProjectManager = Depends(get_project_manager),
    project_file_manager: ProjectFileManager = Depends(get_project_file_manager),
) -> dict:
    """Return a deterministic (non-LLM) README covering what was actually generated and how to run it."""
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    backend_files = project_file_manager.list_written(project_id, "backend")
    frontend_files = project_file_manager.list_written(project_id, "frontend")
    markdown = build_run_instructions(project.name, project.description, backend_files, frontend_files)
    return {"project_id": project_id, "markdown": markdown}


@router.get("/projects/{project_id}/download")
def download_project(
    project_id: str,
    project_manager: ProjectManager = Depends(get_project_manager),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    project_file_manager: ProjectFileManager = Depends(get_project_file_manager),
) -> Response:
    """Zip and return every real generated file in the project directory for project_id, plus RUN_INSTRUCTIONS.md."""
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_dir = workspace_manager.get_workspace_path(project_id) / "project"
    backend_files = project_file_manager.list_written(project_id, "backend")
    frontend_files = project_file_manager.list_written(project_id, "frontend")

    if not project_dir.exists() or not any(p.is_file() for p in project_dir.rglob("*")):
        raise HTTPException(status_code=404, detail="No generated files yet -- run the dev team stages first")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(project_dir.rglob("*")):
            if file_path.is_file():
                if ".attempt-" in file_path.name or "__pycache__" in str(file_path):
                    continue
                arcname = str(file_path.relative_to(project_dir)).replace("\\", "/")
                archive.write(file_path, arcname=arcname)

        if "RUN_INSTRUCTIONS.md" not in archive.namelist():
            archive.writestr(
                "RUN_INSTRUCTIONS.md",
                build_run_instructions(project.name, project.description, backend_files, frontend_files),
            )

    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in project.name.lower().replace(" ", "-")) or project_id
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )
