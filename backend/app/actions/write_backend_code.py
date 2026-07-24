from __future__ import annotations

from ..artifact.manager import ArtifactManager
from ..prompt.backend_builder import BackendPromptBuilder
from ..workspace.project_files import ProjectFileManager
from .write_project_files import WriteProjectFilesAction


class WriteBackendCodeAction(WriteProjectFilesAction):
    """BackendDeveloper's action: implements the approved File Plan's backend-assigned files,
    one focused LLM call per file, written for real via ProjectFileManager."""

    name = "WriteBackendFiles"
    description = "Implement the approved File Plan's backend-assigned files."
    area = "backend"
    responsible_stage = "backend"
    role_label = "Backend Developer"

    def __init__(
        self,
        prompt_builder: BackendPromptBuilder | None = None,
        artifact_manager: ArtifactManager | None = None,
        project_file_manager: ProjectFileManager | None = None,
    ) -> None:
        """Wire the Backend prompt builder this action uses."""
        super().__init__(prompt_builder or BackendPromptBuilder(), artifact_manager, project_file_manager)
