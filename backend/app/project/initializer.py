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
        """Initialize the project's memory namespace.

        Sets state to CLARIFYING so manager.run() enters domain-research →
        Q&A → StrategicReview → ProductOwner on the next workflow/start call.

        Previously this called run_stage("ProductOwner", ...) directly, which
        skipped domain research, Q&A, and StrategicReview entirely, leaving
        ProductOwner with no ClarificationArtifact or StrategicBrief and
        producing an empty artifact on every new project.
        """
        logger.info("initializing project: project_id=%s name=%s", project.project_id, project.name)
        self.memory_manager.initialize(project.project_id)
        # Transition to CLARIFYING so the pipeline entrypoint triggers Q&A.
        from ..shared.enums.project_state import ProjectState
        workspace = getattr(self.workflow_manager, "workspace_manager", None) or getattr(self.workflow_manager, "workspace", None)
        if workspace is not None:
            workspace.update_state(project.project_id, ProjectState.CLARIFYING)
        return project
