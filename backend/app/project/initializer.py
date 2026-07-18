from __future__ import annotations

from pathlib import Path

from ..memory.manager import MemoryManager
from ..shared.models.project import Project
from ..workspace.manager import WorkspaceManager
from ..workflow.manager import WorkflowManager


class ProjectInitializer:
    def __init__(self) -> None:
        self.memory_manager = MemoryManager()
        self.workspace_manager = WorkspaceManager(Path(__file__).resolve().parents[2])
        self.workflow_manager = WorkflowManager()

    def initialize(self, project: Project) -> Project:
        self.workspace_manager.create_workspace(project.name)
        self.memory_manager.initialize(project.name)
        self.workflow_manager.run_stage("ProductOwner", f"Initialize project {project.name}")
        return project
