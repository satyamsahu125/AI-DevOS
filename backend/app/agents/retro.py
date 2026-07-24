from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_retrospective import WriteRetrospectiveAction
from ..llm.manager import LLMManager
from ..prompt.retro_builder import RetroPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class RetroAgent(BaseAgent):
    """Retro agent: summarizes the sprint via WriteRetrospectiveAction.

    Prompt from gstack's /retro persona. Output schema: SprintRetrospective.
    """

    artifact_name = "retro-output"

    def __init__(
        self,
        prompt_builder: RetroPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteRetrospectiveAction."""
        return WriteRetrospectiveAction(self._prompt_builder)
