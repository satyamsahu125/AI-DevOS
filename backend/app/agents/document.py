from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_documentation import WriteDocumentationAction
from ..artifact.manager import ArtifactManager
from ..execution.project_reader import ProjectReader
from ..execution.project_writer import ProjectWriter
from ..llm.manager import LLMManager
from ..prompt.documentation_builder import DocumentationPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DocumentAgent(BaseAgent):
    """Document agent: generates and writes a complete README.md to disk via WriteDocumentationAction."""

    artifact_name = "document-output"

    def __init__(
        self,
        prompt_builder: DocumentationPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        project_writer: ProjectWriter | None = None,
        project_reader: ProjectReader | None = None,
        artifact_manager: ArtifactManager | None = None,
    ) -> None:
        self.project_writer = project_writer or ProjectWriter()
        self.project_reader = project_reader or ProjectReader()
        self.artifact_manager = artifact_manager
        self._prompt_builder = prompt_builder or DocumentationPromptBuilder(self.project_reader, self.artifact_manager)
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteDocumentationAction."""
        return WriteDocumentationAction(
            prompt_builder=self._prompt_builder,
            project_writer=self.project_writer,
            project_reader=self.project_reader,
            artifact_manager=self.artifact_manager,
        )
