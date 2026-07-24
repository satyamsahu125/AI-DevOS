from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_deployment import WriteDeploymentAction
from ..llm.manager import LLMManager
from ..prompt.devops_builder import DevOpsPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DevOpsAgent(BaseAgent):
    """DevOps agent: produces structured deployment configuration for an approved implementation via WriteDeploymentAction."""

    artifact_name = "devops"

    def __init__(
        self,
        prompt_builder: DevOpsPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteDeploymentAction."""
        return WriteDeploymentAction(self._prompt_builder)
