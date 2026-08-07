from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_security_report import WriteSecurityReportAction
from ..llm.manager import LLMManager
from ..prompt.security_builder import SecurityPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class SecurityAgent(BaseAgent):
    """Security agent: audits the implementation via WriteSecurityReportAction.

    Prompt from gstack's /cso persona. Output schema: SecurityReport.
    """

    artifact_name = "security-output"

    def __init__(
        self,
        prompt_builder: SecurityPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteSecurityReportAction."""
        return WriteSecurityReportAction(self._prompt_builder)
