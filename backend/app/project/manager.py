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

    def create_project(self, request: ProjectRequest) -> ProjectResponse:
        """Create, persist, and initialize a new project from request."""
        if not request.name.strip():
            raise ApplicationException("project name is required")
        project_id = str(uuid.uuid4())
        logger.info("creating project: project_id=%s name=%s", project_id, request.name)
        workspace_root = self.workspace_manager.create_workspace(project_id, request.name, request.description)
        project = Project(
            project_id=project_id,
            name=request.name,
            description=request.description,
            workspace_path=str(workspace_root),
        )
        self.repository.save(project)
        self.initializer.initialize(project)
        logger.info("project created: project_id=%s", project.project_id)
        return ProjectResponse(project=project, success=True, message="project created")
