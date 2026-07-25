from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_scrum_plan import WriteScrumPlanAction
from ..llm.manager import LLMManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class ScrumMasterAgent(BaseAgent):
    """Scrum Master agent that generates ScrumPlan for the sprint."""

    artifact_name = "scrum_master"

    def __init__(self, llm_manager: LLMManager | None = None, primary_action: BaseAction | None = None) -> None:
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return WriteScrumPlanAction()
