"""preview.py — Live app preview API for AI DevOS.

R5: Exposes preview status, control, and reverse proxy endpoints.

The reverse proxy at /preview/{project_id}/{path} forwards requests to the
subprocess preview process. The preview process is started automatically by
PipelineSupervisor after each successful sprint sandbox run.

Note: httpx is a dependency (added to requirements.txt). Falls back gracefully
if httpx is not available (preview proxy returns 503).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..workspace.manager import WorkspaceManager
from .dependencies import get_workspace_manager

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_preview_manager():
    """Resolve PreviewManager from DI container (lazy import to avoid circular deps)."""
    try:
        from ..kernel.container import get_container
        container = get_container()
        return getattr(container, "_preview_manager", None) or container._dependencies.resolve("preview_manager")
    except Exception:
        return None


@router.get("/projects/{project_id}/preview/status")
@router.get("/api/projects/{project_id}/preview/status")
def get_preview_status(
    project_id: str,
    workspace: WorkspaceManager = Depends(get_workspace_manager),
):
    """R5: Return the current preview status for a project.

    Status values: "not_running", "disabled", "starting", "running", "crashed"
    When running, also returns port and url (/preview/{project_id}/).
    """
    if not workspace.get_workspace_path(project_id).exists():
        raise HTTPException(status_code=404, detail="Project not found")

    pm = _get_preview_manager()
    if pm is None:
        return {"status": "disabled", "project_id": project_id}

    status = pm.health(project_id)
    return {"project_id": project_id, **status}


@router.post("/projects/{project_id}/preview/restart")
@router.post("/api/projects/{project_id}/preview/restart")
def restart_preview(
    project_id: str,
    workspace: WorkspaceManager = Depends(get_workspace_manager),
):
    """R5: Restart the preview process for a project.

    Stops the existing process and starts a fresh one. Useful after
    a new sprint updates the generated code.
    """
    if not workspace.get_workspace_path(project_id).exists():
        raise HTTPException(status_code=404, detail="Project not found")

    pm = _get_preview_manager()
    if pm is None:
        raise HTTPException(status_code=503, detail="Preview not available (PREVIEW_ENABLED=false)")

    port = pm.restart(project_id)
    if port is None:
        return {"project_id": project_id, "success": False, "message": "Preview restart failed — no running preview to restart"}
    return {"project_id": project_id, "success": True, "port": port, "url": f"/preview/{project_id}/"}


@router.delete("/projects/{project_id}/preview")
@router.delete("/api/projects/{project_id}/preview")
def stop_preview(
    project_id: str,
    workspace: WorkspaceManager = Depends(get_workspace_manager),
):
    """R5: Stop the preview process for a project."""
    if not workspace.get_workspace_path(project_id).exists():
        raise HTTPException(status_code=404, detail="Project not found")

    pm = _get_preview_manager()
    if pm is None:
        return {"project_id": project_id, "stopped": False, "message": "Preview not enabled"}

    pm.stop(project_id)
    return {"project_id": project_id, "stopped": True}


@router.get("/projects/{project_id}/preview/logs")
@router.get("/api/projects/{project_id}/preview/logs")
def get_preview_logs(
    project_id: str,
    lines: int = 50,
    workspace: WorkspaceManager = Depends(get_workspace_manager),
):
    """R5: Return last N lines from the preview process stderr (for debugging)."""
    if not workspace.get_workspace_path(project_id).exists():
        raise HTTPException(status_code=404, detail="Project not found")

    pm = _get_preview_manager()
    if pm is None:
        return {"project_id": project_id, "logs": []}

    log_lines = pm.get_preview_logs(project_id, lines=min(lines, 200))
    return {"project_id": project_id, "logs": log_lines}


@router.api_route(
    "/preview/{project_id}/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_preview(project_id: str, path: str, request: Request):
    """R5: Reverse proxy to the project's preview subprocess.

    Forwards all methods to http://127.0.0.1:{port}/{path}.
    Returns 503 if the preview process is not running or not ready.
    """
    pm = _get_preview_manager()
    if pm is None:
        raise HTTPException(status_code=503, detail="Preview not enabled (PREVIEW_ENABLED=false)")

    status = pm.health(project_id)
    if status.get("status") not in ("running", "starting"):
        raise HTTPException(
            status_code=503,
            detail=f"Preview not running (status: {status.get('status', 'unknown')})",
        )

    port = status.get("port")
    if not port:
        raise HTTPException(status_code=503, detail="Preview port unavailable")

    target_url = f"http://127.0.0.1:{port}/{path}"
    if request.query_string:
        target_url += f"?{request.query_string.decode()}"

    try:
        import httpx
        body = await request.body()
        forward_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length")
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                content=body,
                follow_redirects=True,
            )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            headers=dict(resp.headers),
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="httpx not installed — pip install httpx to enable preview proxy",
        )
    except Exception as exc:
        logger.warning("[preview_proxy] proxy error for %s/%s: %s", project_id, path, exc)
        raise HTTPException(status_code=502, detail=f"Preview proxy error: {exc}")
