from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_requirements import WriteRequirementsAction
from ..llm.manager import LLMManager
from ..prompt.product_owner_builder import ProductOwnerPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ProductOwnerAgent(BaseAgent):
    """Product Owner agent: turns raw input into a structured requirements artifact via WriteRequirementsAction."""

    artifact_name = "product-owner-output"

    def __init__(
        self,
        prompt_builder: ProductOwnerPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteRequirementsAction."""
        return WriteRequirementsAction(self._prompt_builder)
