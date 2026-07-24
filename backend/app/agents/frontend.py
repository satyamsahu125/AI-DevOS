from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_frontend_code import WriteFrontendCodeAction
from ..artifact.manager import ArtifactManager
from ..llm.manager import LLMManager
from ..prompt.frontend_builder import FrontendPromptBuilder
from ..workspace.project_files import ProjectFileManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class FrontendDeveloperAgent(BaseAgent):
    """Frontend Developer agent: implements the approved File Plan's frontend-assigned files,
    one focused LLM call per file, via WriteFrontendCodeAction."""

    artifact_name = "frontend"

    def __init__(
        self,
        prompt_builder: FrontendPromptBuilder | None = None,
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
        """Build this agent's default action: WriteFrontendCodeAction."""
        return WriteFrontendCodeAction(self._prompt_builder, self._artifact_manager, self._project_file_manager)
