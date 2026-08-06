import io
import json
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Response

from ..execution.project_validator import ProjectValidator
from ..memory.manager import MemoryManager
from ..project.manager import ProjectManager
from ..workspace.manager import WorkspaceManager
from ..workspace.project_files import ProjectFileManager
from ..workspace.project_readme import build_run_instructions
from .dependencies import get_memory_manager, get_project_file_manager, get_project_manager, get_project_validator, get_workspace_manager
from .middleware.jwt_auth import get_current_user

router = APIRouter()


def _assert_project_access(project, user) -> None:
    if user.role == "admin":
        return
    if project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access to this project is not permitted")


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
    user=Depends(get_current_user),
) -> dict:
    """Return a deterministic (non-LLM) README covering what was actually generated and how to run it."""
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)
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
    project_validator: ProjectValidator = Depends(get_project_validator),
    memory: MemoryManager = Depends(get_memory_manager),
    user=Depends(get_current_user),
) -> Response:
    """Zip and return every real generated file in the project directory for project_id.

    R3: Includes RUN_INSTRUCTIONS.md (with Docker section), VALIDATION_REPORT.md,
    and VERIFICATION_REPORT.md (from R2 sandbox results). Dotfiles (Dockerfile,
    .dockerignore, .github/) are included via rglob("*").
    """
    project = project_manager.repository.load(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    _assert_project_access(project, user)

    project_dir = workspace_manager.get_workspace_path(project_id) / "project"
    backend_files = project_file_manager.list_written(project_id, "backend")
    frontend_files = project_file_manager.list_written(project_id, "frontend")

    if not project_dir.exists() or not any(p.is_file() for p in project_dir.rglob("*")):
        raise HTTPException(status_code=404, detail="No generated files yet -- run the dev team stages first")

    val_result = project_validator.validate(project_id, skip_install=True)
    def step_pass(name: str) -> bool:
        s = val_result.steps.get(name)
        return s.passed if s else False

    report_content = f"""# Project Validation Report
Project: {project_id}
Overall Result: {"PASSED" if val_result.passed else "FAILED"}

## Step Results
- **Install Dependencies**: {"PASS" if step_pass("install") else "FAIL"}
- **Python Compilation**: {"PASS" if step_pass("compile") else "FAIL"}
- **Project Startup**: {"PASS" if step_pass("startup") else "FAIL"}
- **Automated Tests**: {"PASS" if step_pass("tests") else "FAIL"}

## Summary
{val_result.error_summary or "All checks passed successfully."}
"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(project_dir.rglob("*")):
            if file_path.is_file():
                if ".attempt-" in file_path.name or "__pycache__" in str(file_path):
                    continue
                arcname = str(file_path.relative_to(project_dir)).replace("\\", "/")
                archive.write(file_path, arcname=arcname)

        # R3: detect if Dockerfile was generated (so Docker section appears in README)
        has_dockerfile = any("Dockerfile" in n for n in archive.namelist())

        if "RUN_INSTRUCTIONS.md" not in archive.namelist():
            archive.writestr(
                "RUN_INSTRUCTIONS.md",
                build_run_instructions(project.name, project.description, backend_files, frontend_files, has_dockerfile=has_dockerfile),
            )
        archive.writestr("VALIDATION_REPORT.md", report_content)

        # R2/R3: include sandbox verification report
        verification_md = _build_verification_report(project_id, memory)
        archive.writestr("VERIFICATION_REPORT.md", verification_md)

    safe_name = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in project.name.lower().replace(" ", "-")) or project_id
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.zip"'},
    )


def _build_verification_report(project_id: str, memory: MemoryManager) -> str:
    """Build VERIFICATION_REPORT.md from stored sandbox results.

    R2/R3: Reads the latest sandbox lint/test/build results stored by
    PipelineSupervisor._run_sandbox() and formats them as markdown.
    """
    try:
        raw = memory.load(project_id, "sandbox:latest")
        if not raw:
            return "# Verification Report\n\nNo sandbox verification results available.\n"
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return "# Verification Report\n\nCould not load sandbox results.\n"

    lint = data.get("lint", {})
    build = data.get("build", {})
    test = data.get("test", {})
    sprint = data.get("sprint", 0)
    stack = data.get("stack", "unknown")

    lint_errors = lint.get("errors", [])
    lint_count = lint.get("error_count", len(lint_errors))
    build_ok = build.get("success", True)
    build_errors = build.get("errors", [])
    test_passed = test.get("passed", 0)
    test_total = test.get("total", 0)
    test_failures = test.get("failures", [])

    lines = [
        f"# Verification Report — Sprint {sprint}",
        f"",
        f"Stack: `{stack}`",
        f"",
        f"## Lint",
        f"Errors: {lint_count}",
    ]
    if lint_errors:
        for e in lint_errors[:30]:
            lines.append(f"- `{e.get('file','?')}:{e.get('line',0)}` — {e.get('message','')}")
    else:
        lines.append("No lint errors detected.")

    lines += [
        f"",
        f"## Build",
        f"Status: {'PASSED ✅' if build_ok else 'FAILED ❌'}",
    ]
    if build_errors:
        for e in build_errors[:10]:
            lines.append(f"- {e}")

    lines += [
        f"",
        f"## Tests",
        f"Passed: {test_passed}/{test_total}",
    ]
    if test_failures:
        for f in test_failures[:20]:
            lines.append(f"- **{f.get('test_name','?')}**: {f.get('error','')}")
    elif test_total == 0:
        lines.append("No tests found.")

    return "\n".join(lines) + "\n"
