from __future__ import annotations

from ..actions.base_action import BaseAction
from ..actions.write_sprint_delta import WriteSprintDeltaAction
from ..llm.manager import LLMManager
from .base_agent import BaseAgent


class SprintDeltaAgent(BaseAgent):
    """Decides create/update/patch operation per file before FileStructurePlanner runs.

    Produces a SprintDeltaArtifact that FileStructurePlanner consumes to set
    operation/change_description reliably, eliminating the fragile pattern of
    letting the FilePlan LLM infer operations from a raw EXISTING FILES list.

    Failure is non-blocking — if the LLM call fails, FileStructurePlanner
    falls back to its own FileRegistry-based inference.
    """

    artifact_name = "sprint_delta"

    def __init__(
        self,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        artifact_manager: object | None = None,
        file_registry: object | None = None,
    ) -> None:
        self._artifact_manager = artifact_manager
        self._file_registry = file_registry
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return WriteSprintDeltaAction(
            artifact_manager=self._artifact_manager,
            file_registry=self._file_registry,
        )
