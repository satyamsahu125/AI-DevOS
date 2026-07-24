from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_architecture import WriteArchitectureAction
from ..llm.manager import LLMManager
from ..prompt.architect_builder import ArchitectPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ArchitectAgent(BaseAgent):
    """Architect agent: turns an approved requirements artifact into a structured architecture via WriteArchitectureAction."""

    artifact_name = "architecture"

    def __init__(
        self,
        prompt_builder: ArchitectPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteArchitectureAction."""
        return WriteArchitectureAction(self._prompt_builder)
