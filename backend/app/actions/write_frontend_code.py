from __future__ import annotations

from ..artifact.manager import ArtifactManager
from ..prompt.frontend_builder import FrontendPromptBuilder
from ..workspace.project_files import ProjectFileManager
from .write_project_files import WriteProjectFilesAction


class WriteFrontendCodeAction(WriteProjectFilesAction):
    """FrontendDeveloper's action: implements the approved File Plan's frontend-assigned files,
    one focused LLM call per file, written for real via ProjectFileManager."""

    name = "WriteFrontendFiles"
    description = "Implement the approved File Plan's frontend-assigned files."
    area = "frontend"
    responsible_stage = "frontend"
    role_label = "Frontend Developer"

    def __init__(
        self,
        prompt_builder: FrontendPromptBuilder | None = None,
        artifact_manager: ArtifactManager | None = None,
        project_file_manager: ProjectFileManager | None = None,
    ) -> None:
        """Wire the Frontend prompt builder this action uses."""
        super().__init__(prompt_builder or FrontendPromptBuilder(), artifact_manager, project_file_manager)
