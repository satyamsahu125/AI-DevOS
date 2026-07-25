from __future__ import annotations

from ..actions.base_action import BaseAction
from ..actions.clarify_requirements import ClarifyRequirementsAction
from ..llm.manager import LLMManager
from .base_agent import BaseAgent


class ClarificationAgent(BaseAgent):
    """Requirements Clarification agent (runs before ProductOwner)."""

    artifact_name = "clarification-report"

    def __init__(self, llm_manager: LLMManager | None = None, primary_action: BaseAction | None = None) -> None:
        """Store LLMManager and build default action."""
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return ClarifyRequirementsAction()
