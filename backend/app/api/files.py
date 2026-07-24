import io
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Response

from ..project.manager import ProjectManager
from ..workspace.project_files import ProjectFileManager
from ..workspace.project_readme import build_run_instructions
from .dependencies import get_project_file_manager, get_project_manager

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
    project_file_manager: ProjectFileManager = Depends(get_project_file_manager),
) -> Response:
    """Zip and return every real generated file (backend + frontend) for project_id, plus a
    generated RUN_INSTRUCTIONS.md at the archive root."""
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    backend_files = project_file_manager.list_written(project_id, "backend")
    frontend_files = project_file_manager.list_written(project_id, "frontend")
    if not backend_files and not frontend_files:
        raise HTTPException(status_code=404, detail="No generated files yet -- run the Backend/Frontend Developer stages first")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for area, files in (("backend", backend_files), ("frontend", frontend_files)):
            area_root = project_file_manager.area_dir(project_id, area)
            for relative_path in files:
                archive.write(area_root / relative_path, arcname=f"{area}/{relative_path}")
        archive.writestr(
            "RUN_INSTRUCTIONS.md",
            build_run_instructions(project.name, project.description, backend_files, frontend_files),
        )

    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in project.name) or project_id
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )
