from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_backend_code import WriteBackendCodeAction
from ..artifact.manager import ArtifactManager
from ..llm.manager import LLMManager
from ..prompt.backend_builder import BackendPromptBuilder
from ..workspace.project_files import ProjectFileManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class BackendDeveloperAgent(BaseAgent):
    """Backend Developer agent: implements the approved File Plan's backend-assigned files,
    one focused LLM call per file, via WriteBackendCodeAction."""

    artifact_name = "backend"

    def __init__(
        self,
        prompt_builder: BackendPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        artifact_manager: ArtifactManager | None = None,
        project_file_manager: ProjectFileManager | None = None,
    ) -> None:
        """Wire this agent's prompt builder, the ArtifactManager/ProjectFileManager its action
        uses to fetch the File Plan/Architecture and write real files, and (via BaseAgent) its
        LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        self._artifact_manager = artifact_manager
        self._project_file_manager = project_file_manager
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteBackendCodeAction."""
        return WriteBackendCodeAction(self._prompt_builder, self._artifact_manager, self._project_file_manager)
