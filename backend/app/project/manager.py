from __future__ import annotations

import uuid
from pathlib import Path

from ..shared.dto.project_request import ProjectRequest
from ..shared.dto.project_response import ProjectResponse
from ..shared.exceptions import ApplicationException
from ..shared.models.project import Project
from ..workspace.manager import WorkspaceManager
from .initializer import ProjectInitializer
from .repository import ProjectRepository


class ProjectManager:
    def __init__(self, repository: ProjectRepository | None = None) -> None:
        self.repository = repository or ProjectRepository()
        self.initializer = ProjectInitializer()
        self.workspace_manager = WorkspaceManager(Path(__file__).resolve().parents[2])

    def create_project(self, request: ProjectRequest) -> ProjectResponse:
        if not request.name.strip():
            raise ApplicationException("project name is required")
        workspace_root = self.workspace_manager.create_workspace(request.name)
        project = Project(
            project_id=str(uuid.uuid4()),
            name=request.name,
            description=request.description,
            workspace_path=str(workspace_root),
        )
        self.repository.save(project)
        self.initializer.initialize(project)
        return ProjectResponse(project=project, success=True, message="project created")
