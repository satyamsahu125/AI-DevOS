from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_design import WriteDesignAction
from ..llm.manager import LLMManager
from ..prompt.designer_builder import DesignerPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DesignerAgent(BaseAgent):
    """Designer agent: produces the complete UI/UX design specification via WriteDesignAction.

    Runs after Architect, before Security and FrontendDeveloper (see
    workflow/dependency_graph.py). FrontendDeveloper and QA both depend on
    this stage's output -- no frontend code should ever be written without
    an approved design spec.
    """

    artifact_name = "designer-output"

    def __init__(
        self,
        prompt_builder: DesignerPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteDesignAction."""
        return WriteDesignAction(self._prompt_builder)
