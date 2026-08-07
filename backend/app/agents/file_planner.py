from __future__ import annotations

from ..actions.base_action import BaseAction
from ..actions.write_file_plan import WriteFilePlanAction
from ..artifact.manager import ArtifactManager
from ..llm.manager import LLMManager
from ..prompt.file_plan_builder import FilePlanPromptBuilder
from ..workspace.file_registry import FileRegistry
from .base_agent import BaseAgent


class FilePlannerAgent(BaseAgent):
    """File Structure Planner agent (Senior Tech Lead)."""

    artifact_name = "file_plan"

    def __init__(
        self,
        prompt_builder: FilePlanPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        artifact_manager: ArtifactManager | None = None,
        file_registry: FileRegistry | None = None,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._artifact_manager = artifact_manager
        # Phase 8: optional FileRegistry so Sprint 2+ prompts include existing files
        self._file_registry = file_registry
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return WriteFilePlanAction(self._prompt_builder, self._artifact_manager, self._file_registry)


FileStructurePlannerAgent = FilePlannerAgent
