from __future__ import annotations

import logging

from ..memory.manager import MemoryManager
from ..shared.models.project import Project
from ..workflow.manager import WorkflowManager

logger = logging.getLogger(__name__)


class ProjectInitializer:
    """Initializes a newly created project's memory and runs its first workflow stage.

    The workspace itself (directories + project.json) is already created by
    ProjectManager before this runs -- re-creating it here would reset
    project.json's stages_completed/current_stage back to empty every time
    a project is (re-)initialized, so this only touches memory and the
    workflow.
    """

    def __init__(self, workflow_manager: WorkflowManager | None = None) -> None:
        """Wire the memory and workflow managers used during initialization."""
        self.memory_manager = MemoryManager()
        self.workflow_manager = workflow_manager or WorkflowManager()

    def initialize(self, project: Project) -> Project:
        """Initialize the project's memory namespace and run its first workflow stage.

        Uses project.description as the actual ProductOwner task content --
        previously this only ever sent "Initialize project {name}", silently
        discarding the user's real build request and leaving the LLM with
        nothing concrete to work from (observed bug: a "calci" / "Create a
        basic calculator app" project produced an unrelated invoice-app spec).
        """
        logger.info("initializing project: project_id=%s name=%s", project.project_id, project.name)
        self.memory_manager.initialize(project.project_id)
        description = project.description.strip()
        content = f"Build: {description}\n(Project name: {project.name})" if description else f"Initialize project {project.name}"
        self.workflow_manager.run_stage(project.project_id, "ProductOwner", content)
        return project
