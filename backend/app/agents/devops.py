from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_deployment import WriteDeploymentAction
from ..execution.file_validator import FileValidator
from ..execution.project_reader import ProjectReader
from ..execution.project_writer import ProjectWriter
from ..llm.manager import LLMManager
from ..prompt.devops_builder import DevOpsPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DevOpsAgent(BaseAgent):
    """DevOps agent: produces Docker, docker-compose, env templates, and CI configs on disk via WriteDeploymentAction."""

    artifact_name = "devops"

    def __init__(
        self,
        prompt_builder: DevOpsPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        project_writer: ProjectWriter | None = None,
        project_reader: ProjectReader | None = None,
        file_validator: FileValidator | None = None,
    ) -> None:
        self.project_writer = project_writer or ProjectWriter()
        self.project_reader = project_reader or ProjectReader()
        self.file_validator = file_validator or FileValidator()
        self._prompt_builder = prompt_builder or DevOpsPromptBuilder(self.project_reader)
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteDeploymentAction."""
        return WriteDeploymentAction(
            prompt_builder=self._prompt_builder,
            project_writer=self.project_writer,
            project_reader=self.project_reader,
            file_validator=self.file_validator,
        )


# Alias: release-phase production deploy is the same agent as DevOpsAgent
ProductionDeployAgent = DevOpsAgent
