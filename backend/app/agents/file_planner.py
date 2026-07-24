from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..actions.write_file_plan import WriteFilePlanAction
from ..artifact.manager import ArtifactManager
from ..llm.manager import LLMManager
from ..prompt.file_plan_builder import FilePlanPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class FileStructurePlannerAgent(BaseAgent):
    """File Structure Planner agent: turns the approved architecture and design spec into a
    concrete, minimal file list via WriteFilePlanAction.

    Runs after Security, before BackendDeveloper/FrontendDeveloper (see
    workflow/dependency_graph.py) -- its output is what lets Backend/Frontend
    generate one focused file at a time instead of inventing an entire app's
    worth of files in a single LLM response.
    """

    artifact_name = "file_plan"

    def __init__(
        self,
        prompt_builder: FilePlanPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        artifact_manager: ArtifactManager | None = None,
    ) -> None:
        """Wire this agent's prompt builder, the ArtifactManager its action uses to fetch the
        approved architecture, and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        self._artifact_manager = artifact_manager
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteFilePlanAction."""
        return WriteFilePlanAction(self._prompt_builder, self._artifact_manager)
