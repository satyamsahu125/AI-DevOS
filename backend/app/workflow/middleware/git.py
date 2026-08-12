"""GitMiddleware — commit approved stage artifacts to project git history.

Single responsibility: after stage approval, create a meaningful git commit
in the project workspace. All git errors are caught and logged; a git failure
never propagates to the caller or blocks the pipeline.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class GitMiddleware:
    """Commits approved stage artifacts to the project workspace git repo.

    Parameters
    ----------
    workspace_manager:
        Provides get_workspace_path(project_id) → Path.
    """

    def __init__(self, workspace_manager: Any) -> None:
        self.workspace_manager = workspace_manager

    def on_approval(self, project_id: str, stage_name: str, artifact: Any) -> None:
        """Commit the approved artifact. Non-fatal — never raises."""
        try:
            from ...workspace.git_manager import GitManager
            workspace_path = self.workspace_manager.get_workspace_path(project_id)
            git = GitManager(workspace_path)
            raw = getattr(artifact, "content", "") or ""
            summary = raw[:100].replace("\n", " ").strip() or stage_name
            commit_hash = git.commit_stage(stage_name, summary)
            if commit_hash:
                logger.debug(
                    "git commit: project=%s stage=%s hash=%s",
                    project_id, stage_name, commit_hash,
                )
        except Exception as exc:
            logger.debug("GitMiddleware.on_approval skipped for %s/%s: %s",
                         project_id, stage_name, exc)
