from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_qa_report import WriteQAReportAction
from ..llm.manager import LLMManager
from ..prompt.qa_builder import QAPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class QAAgent(BaseAgent):
    """QA agent: validates an implementation and produces a structured QA report via WriteQAReportAction."""

    artifact_name = "qa"

    def __init__(
        self,
        prompt_builder: QAPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteQAReportAction."""
        return WriteQAReportAction(self._prompt_builder)
