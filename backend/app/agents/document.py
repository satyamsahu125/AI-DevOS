from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_documentation_update import WriteDocumentationUpdateAction
from ..llm.manager import LLMManager
from ..prompt.document_builder import DocumentPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DocumentAgent(BaseAgent):
    """Document agent: updates project docs via WriteDocumentationUpdateAction.

    Prompt from gstack's /document-release persona. Output schema: DocumentationUpdate.
    """

    artifact_name = "document-output"

    def __init__(
        self,
        prompt_builder: DocumentPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteDocumentationUpdateAction."""
        return WriteDocumentationUpdateAction(self._prompt_builder)
