import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from ..artifact.manager import ArtifactManager
from ..execution.project_validator import ProjectValidator
from ..memory.manager import MemoryManager
from ..project.manager import ProjectManager
from ..shared.dto.project_request import ProjectRequest
from ..shared.dto.project_response import ProjectResponse
from ..shared.enums.project_state import ProjectState
from ..shared.models.project import Project
from ..workflow.manager import WorkflowManager
from ..workspace.manager import WorkspaceManager
from ..workspace.project_files import ProjectFileManager
from ..llm.cost_tracker import CostTracker
from .dependencies import (
    get_artifact_manager,
    get_cost_tracker,
    get_memory_manager,
    get_project_file_manager,
    get_project_manager,
    get_project_validator,
    get_workflow_manager,
    get_workspace_manager,
)
from .middleware.jwt_auth import get_current_user

router = APIRouter()

_MAX_NAME_LENGTH = 100
# Phase 6: per-owner project count cap.
# Overridable via MAX_PROJECTS_PER_KEY env var. Default 20.
MAX_PROJECTS_PER_KEY: int = int(os.getenv("MAX_PROJECTS_PER_KEY", "20"))


def _assert_project_access(project: Project, user) -> None:
    """Raise 403 if the caller does not own the project and is not an admin.

    Admins can access any project; regular users can only access their own.
    """
    if user.role == "admin":
        return
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access to this project is not permitted")
_MAX_DESCRIPTION_LENGTH = 2000
_VALID_NAME_PATTERN = __import__("re").compile(r"^[A-Za-z0-9 _\-]+$")


def _validate_project_request(request: ProjectRequest) -> None:
    """Validate project name and description fields.

    Phase 6: unbounded descriptions get embedded in every LLM prompt, causing
    unexpected token cost. Name validation prevents injection via project names.

    Raises HTTPException 422 on invalid input.
    """
    name = (request.name or "").strip()
    description = (request.description or "").strip()

    if not name:
        raise HTTPException(status_code=422, detail="name is required and cannot be empty")
    if len(name) > _MAX_NAME_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"name must be at most {_MAX_NAME_LENGTH} characters (got {len(name)})",
        )
    if not _VALID_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=422,
            detail="name must contain only letters, numbers, spaces, hyphens, or underscores",
        )
    if len(description) > _MAX_DESCRIPTION_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=f"description must be at most {_MAX_DESCRIPTION_LENGTH} characters (got {len(description)})",
        )


def _enforce_project_limit(manager: ProjectManager, user_id: str) -> None:
    """Raise HTTP 429 if the owner already has MAX_PROJECTS_PER_KEY projects.

    Counting key is user.id (JWT sub claim, or 'anonymous' when AUTH_ENABLED=false).
    This keeps the limit per authenticated identity, consistent with owner_id on Project.
    """
    existing = manager.repository.list_by_owner(user_id)
    if len(existing) >= MAX_PROJECTS_PER_KEY:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Project limit reached. Maximum {MAX_PROJECTS_PER_KEY} projects per user. "
                f"Delete an existing project or set MAX_PROJECTS_PER_KEY to raise the limit."
            ),
        )


@router.post("/projects", response_model=ProjectResponse, status_code=201)
def create_project(
    request: ProjectRequest,
    manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> ProjectResponse:
    _validate_project_request(request)
    _enforce_project_limit(manager, user.id)
    return manager.create_project(request, user_id=user.id)


@router.post("/projects/create-and-run", status_code=201)
def create_and_run_project(
    request: ProjectRequest,
    background_tasks: BackgroundTasks,
    manager: ProjectManager = Depends(get_project_manager),
    workflow_manager: WorkflowManager = Depends(get_workflow_manager),
    user=Depends(get_current_user),
) -> dict:
    _validate_project_request(request)
    _enforce_project_limit(manager, user.id)
    project_resp = manager.create_project(request, user_id=user.id)
    content = request.description or f"Initialize project {project_resp.project_id}"
    background_tasks.add_task(workflow_manager.run, project_resp.project_id, content)
    return {
        "id": project_resp.project_id,
        "name": project_resp.name,
        "description": project_resp.description,
        "status": "running",
        "state": "initializing"
    }


@router.get("/projects")
def list_projects(
    manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> list[dict]:
    """Return projects owned by the current user (admins see all)."""
    if user.role == "admin":
        projects = manager.repository.list_projects()
    else:
        projects = manager.repository.list_by_owner(user.id)
    return [
        {
            "project_id": project.project_id,
            "name": project.name,
            "status": project.status,
            "current_stage": project.current_stage.value,
            "created_at": project.created_at.isoformat(),
        }
        for project in projects
    ]


@router.get("/projects/{project_id}")
def get_project(
    project_id: str,
    manager: ProjectManager = Depends(get_project_manager),
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    artifact_manager: ArtifactManager = Depends(get_artifact_manager),
    user=Depends(get_current_user),
) -> dict:
    """Return the project's static record merged with its live workspace progress and approved artifacts."""
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)

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

    data = {
        "project_id": project.project_id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "current_stage": workspace_state.get("current_stage", project.current_stage.value),
        "stages_completed": workspace_state.get("stages_completed", []),
        "artifacts": artifacts,
        "workspace_path": project.workspace_path,
    }

    if data["current_stage"] == "clarifying" or data["status"] == "paused":
        qa = workspace_manager.get_qa_session(project_id)
        if qa and "questions" in qa:
            data["clarification_questions"] = [
                q.get("question") for q in qa["questions"] if "question" in q
            ]

    return data

class ClarificationSubmitRequest(BaseModel):
    answers: dict[str, str]


@router.post("/projects/{project_id}/submit-clarifications")
def submit_clarifications(
    project_id: str,
    request: ClarificationSubmitRequest,
    background_tasks: BackgroundTasks,
    workspace_manager: WorkspaceManager = Depends(get_workspace_manager),
    workflow_manager: WorkflowManager = Depends(get_workflow_manager),
    manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
):
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)

    qa = workspace_manager.get_qa_session(project_id)
    questions = qa.get("questions", [])

    for q_idx, q_dict in enumerate(questions):
        q_text = q_dict.get("question", "")
        if q_text in request.answers:
            workspace_manager.save_qa_answer(project_id, q_idx, request.answers[q_text])

    workspace_manager.mark_qa_complete(project_id)
    workspace_manager.update_state(project_id, ProjectState.QA_IN_PROGRESS)
    
    background_tasks.add_task(workflow_manager.run, project_id, "")
    
    return {"status": "success"}


@router.get("/projects/{project_id}/files")
def list_project_files(
    project_id: str,
    project_file_manager: ProjectFileManager = Depends(get_project_file_manager),
    manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Lists all real generated files in project/ directory."""
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    project_dir = project_file_manager.project_root(project_id)
    backend_files = project_file_manager.list_written(project_id, "backend")
    frontend_files = project_file_manager.list_written(project_id, "frontend")

    file_list = []
    if project_dir.exists():
        for p in project_dir.rglob("*"):
            if p.is_file() and not p.name.startswith("_attempt_"):
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
    manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Returns actual content of a generated file."""
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)

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
    user=Depends(get_current_user),
) -> Response:
    """Delete project_id's workspace, project record, artifact rows, and namespaced memory records."""
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    workspace_manager.delete_workspace(project_id)
    manager.repository.delete(project_id)
    artifact_manager.delete_project_artifacts(project_id)
    memory_manager.delete_project(project_id)
    return Response(status_code=204)


@router.get("/projects/{project_id}/validate")
def validate_project(
    project_id: str,
    validator: ProjectValidator = Depends(get_project_validator),
    manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
) -> dict:
    """Run full validation suite on generated project."""
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    result = validator.validate(project_id)
    return {
        "project_id": result.project_id,
        "passed": result.passed,
        "error_summary": result.error_summary,
        "steps": {
            k: {
                "step": v.step,
                "passed": v.passed,
                "output": v.output,
                "errors": v.errors,
                "duration_seconds": v.duration_seconds,
            }
            for k, v in result.steps.items()
        },
        "fixable_errors": result.fixable_errors,
        "test_results": result.test_results,
    }


@router.get("/projects/{project_id}/metrics")
@router.get("/api/projects/{project_id}/metrics")
def get_project_metrics(
    project_id: str,
    tracker: CostTracker = Depends(get_cost_tracker),
    manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
):
    """Return ProjectCostSummary metrics for project_id."""
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    return tracker.get_project_summary(project_id)


@router.get("/projects/{project_id}/metrics/{stage}")
@router.get("/api/projects/{project_id}/metrics/{stage}")
def get_stage_metrics(
    project_id: str,
    stage: str,
    tracker: CostTracker = Depends(get_cost_tracker),
    manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
):
    """Return individual LLM call details for stage under project_id."""
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    return tracker.get_stage_calls(project_id, stage)


@router.get("/projects/{project_id}/sandbox-results")
@router.get("/api/projects/{project_id}/sandbox-results")
def get_sandbox_results(
    project_id: str,
    sprint: int = Query(default=-1, description="Sprint number, -1 for latest"),
    memory: MemoryManager = Depends(get_memory_manager),
    manager: ProjectManager = Depends(get_project_manager),
    user=Depends(get_current_user),
):
    """R2: Return the latest sandbox lint/test/build results for a project.

    Results are stored by PipelineSupervisor._run_sandbox() at 'sandbox:latest'
    after each sprint. The optional `sprint` query param is accepted but
    currently only the latest result is stored (all sprints key to 'sandbox:latest').
    """
    project = manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
    raw = memory.load(project_id, "sandbox:latest")
    if raw is None:
        raise HTTPException(status_code=404, detail="No sandbox results found for this project")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        data = {"raw": str(raw)}
    return data


# NOTE: The download endpoint lives in api/files.py which already handles project zips
# with RUN_INSTRUCTIONS.md and VALIDATION_REPORT.md. R3 enhanced that endpoint to also
# include VERIFICATION_REPORT.md (see api/files.py download_project).
