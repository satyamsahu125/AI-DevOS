from __future__ import annotations

from ..actions.base_action import BaseAction
from ..actions.plan_sprints import PlanSprintsAction
from ..llm.manager import LLMManager
from .base_agent import BaseAgent


class SprintPlannerAgent(BaseAgent):
    """Agile Sprint Planner agent (Senior Engineering Manager)."""

    artifact_name = "sprint-plan"

    def __init__(self, llm_manager: LLMManager | None = None, primary_action: BaseAction | None = None) -> None:
        """Store LLMManager and build default action."""
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return PlanSprintsAction()
