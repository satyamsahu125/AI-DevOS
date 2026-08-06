from __future__ import annotations

import logging
import uuid

from ..shared.dto.project_request import ProjectRequest
from ..shared.dto.project_response import ProjectResponse
from ..shared.exceptions import ApplicationException
from ..shared.models.project import Project
from ..workspace.manager import WorkspaceManager
from .initializer import ProjectInitializer
from .repository import ProjectRepository

logger = logging.getLogger(__name__)


class ProjectManager:
    """Public entry point for creating and initializing a project."""

    def __init__(
        self,
        repository: ProjectRepository | None = None,
        initializer: ProjectInitializer | None = None,
    ) -> None:
        """Wire the repository and initializer used to create a project."""
        self.repository = repository or ProjectRepository()
        self.initializer = initializer or ProjectInitializer()
        self.workspace_manager = WorkspaceManager()

    def create_project(self, request: ProjectRequest, user_id: str = "anonymous") -> ProjectResponse:
        """Create and persist a new project from request.

        Deliberately does NOT run any pipeline stage: project creation must
        never depend on a reachable LLM. The project is born in
        ProjectState.EMPTY and stays there until the user calls
        POST /workflow/start, which is where WorkflowManager.run() (and
        therefore the first LLM call) belongs.

        If persisting the record fails after the workspace directory was
        already created, the workspace is rolled back so a failed create
        can't leave an orphaned directory behind.

        Parameters
        ----------
        request : ProjectRequest
            Name, description, and mode for the new project.
        user_id : str
            The authenticated user's ID from the JWT. Stamped on the project
            as owner_id so all subsequent requests can filter by ownership.
        """
        if not request.name.strip():
            raise ApplicationException("project name is required")
        project_id = str(uuid.uuid4())
        logger.info("creating project: project_id=%s name=%s owner=%s", project_id, request.name, user_id)
        try:
            mode = getattr(request, "mode", "full") or "full"
            workspace_root = self.workspace_manager.create_workspace(project_id, request.name, request.description, mode=mode)
            project = Project(
                project_id=project_id,
                name=request.name,
                description=request.description,
                workspace_path=str(workspace_root),
                owner_id=user_id,
            )
            self.repository.save(project)
        except Exception as exc:
            logger.error("failed to create project: project_id=%s error=%s", project_id, exc)
            try:
                self.workspace_manager.delete_workspace(project_id)
            except Exception:
                logger.warning("workspace rollback failed: project_id=%s", project_id)
            try:
                self.repository.delete(project_id)
            except Exception:
                logger.warning("project record rollback failed: project_id=%s", project_id)
            raise
        logger.info("project created: project_id=%s", project.project_id)
        return ProjectResponse(project=project, success=True, message="project created")
