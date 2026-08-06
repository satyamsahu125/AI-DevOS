"""git.py — Git repository API for AI DevOS projects.

R4: Exposes git log and GitHub push operations for project workspaces.

Security:
- GitHub tokens are accepted in request body only, never stored, never logged.
- All git operations run in the project workspace directory (sandboxed per-project).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..workspace.git_manager import GitManager
from ..workspace.manager import WorkspaceManager
from .dependencies import get_workspace_manager

logger = logging.getLogger(__name__)
router = APIRouter()


class PushRequest(BaseModel):
    repo_url: str
    token: str  # GitHub PAT — never stored


@router.get("/projects/{project_id}/git-log")
@router.get("/api/projects/{project_id}/git-log")
def get_git_log(
    project_id: str,
    workspace: WorkspaceManager = Depends(get_workspace_manager),
):
    """R4: Return commit history for the project's workspace.

    Returns up to 50 commits as {hash, message, date} list.
    Returns empty list if the workspace has no git repository.
    """
    try:
        workspace_path = workspace.get_workspace_path(project_id)
        if not workspace_path.exists():
            raise HTTPException(status_code=404, detail="Project workspace not found")
        git = GitManager(workspace_path)
        commits = git.log()
        return {"project_id": project_id, "commits": commits, "total": len(commits)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[git_api] git-log failed for %s: %s", project_id, exc)
        return {"project_id": project_id, "commits": [], "total": 0, "error": str(exc)}


@router.post("/projects/{project_id}/push-to-github")
@router.post("/api/projects/{project_id}/push-to-github")
def push_to_github(
    project_id: str,
    body: PushRequest,
    workspace: WorkspaceManager = Depends(get_workspace_manager),
):
    """R4: Push the project workspace to a GitHub repository.

    The token is used for this request only and never persisted. The repo_url
    must be an HTTPS GitHub URL (e.g. https://github.com/user/repo).

    Security: the token is embedded in the git remote URL in-process memory only.
    It is never logged, stored in the database, or included in any API response.
    """
    # Basic URL validation
    if not body.repo_url.startswith("https://github.com/"):
        raise HTTPException(
            status_code=422,
            detail="repo_url must be an HTTPS GitHub URL (https://github.com/user/repo)",
        )
    if not body.token:
        raise HTTPException(status_code=422, detail="token is required")

    try:
        workspace_path = workspace.get_workspace_path(project_id)
        if not workspace_path.exists():
            raise HTTPException(status_code=404, detail="Project workspace not found")

        git = GitManager(workspace_path)
        success, message = git.push_to_github(body.repo_url, body.token)

        # IMPORTANT: never include the token in the response
        return {
            "project_id": project_id,
            "success": success,
            "message": message,
            "repo_url": body.repo_url,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[git_api] push-to-github failed for %s: %s", project_id, exc)
        raise HTTPException(status_code=500, detail=f"Push failed: {exc}")
