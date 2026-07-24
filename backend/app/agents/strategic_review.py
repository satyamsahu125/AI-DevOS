from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_strategic_brief import WriteStrategicBriefAction
from ..llm.manager import LLMManager
from ..prompt.strategic_review_builder import StrategicReviewPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class StrategicReviewAgent(BaseAgent):
    """StrategicReview agent: reframes the request via WriteStrategicBriefAction.

    Prompt from gstack's /office-hours + /plan-ceo-review personas. Output schema: StrategicBrief.
    """

    artifact_name = "strategic-review-output"

    def __init__(
        self,
        prompt_builder: StrategicReviewPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteStrategicBriefAction."""
        return WriteStrategicBriefAction(self._prompt_builder)
