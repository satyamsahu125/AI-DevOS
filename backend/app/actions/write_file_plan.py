from __future__ import annotations

import logging
from types import SimpleNamespace

from ..artifact.manager import ArtifactManager
from ..prompt.file_plan_builder import FilePlanPromptBuilder
from ..shared.enums.stage import Stage
from ..shared.schemas.architecture_schema import ArchitectureArtifact
from ..shared.schemas.file_plan_schema import FilePlanArtifact
from .architecture_summary import summarize_architecture
from .base_action import LLMAction

logger = logging.getLogger(__name__)


class WriteFilePlanAction(LLMAction):
    """FileStructurePlanner's action: produces a structured FilePlanArtifact.

    Runs after Security, so its predecessor-message slot (see
    WorkflowEngine._with_predecessor_message) only carries the SecurityReport
    -- the ArchitectureArtifact is further back in the pipeline and isn't
    covered by that single-slot mechanism. This action fetches it directly
    from ArtifactManager, keyed by the project_id the caller puts on
    context, so the plan is always grounded in the real approved
    architecture instead of whatever text happened to survive to this point.
    """

    name = "WriteFilePlan"
    description = "Turn the approved architecture and design into a concrete, minimal file list."
    schema_model = FilePlanArtifact
    system_prompt = (
        "You are a File Structure Planner. Respond with ONLY a single JSON object (no prose outside it) "
        "with this key: files (list of objects with path/module/purpose/responsible_stage, where "
        "responsible_stage is exactly 'backend' or 'frontend'). Keep it minimal: one file per real "
        "responsibility, not one per class or function."
    )

    def __init__(self, prompt_builder: FilePlanPromptBuilder | None = None, artifact_manager: ArtifactManager | None = None) -> None:
        """Wire the File Plan prompt builder and the ArtifactManager used to fetch the approved architecture."""
        super().__init__(prompt_builder or FilePlanPromptBuilder())
        self.artifact_manager = artifact_manager or ArtifactManager()

    def run(self, context: object, llm: object):
        project_id = getattr(context, "project_id", "") or ""
        base_content = getattr(context, "content", "") or ""
        architecture = self._load_architecture(project_id)
        enriched = f"{base_content}\n\n### Architecture Summary\n{summarize_architecture(architecture)}" if architecture else base_content
        return super().run(SimpleNamespace(content=enriched), llm)

    def _load_architecture(self, project_id: str) -> ArchitectureArtifact | None:
        if not project_id:
            return None
        artifact = self.artifact_manager.get_artifact(project_id, Stage.Architect)
        if artifact is None or not artifact.structured_content:
            return None
        try:
            return ArchitectureArtifact.model_validate(artifact.structured_content)
        except Exception as exc:
            logger.debug("%s: failed to parse Architecture: %s", self.name, exc)
            return None
