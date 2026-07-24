from __future__ import annotations

from ..prompt.architect_builder import ArchitectPromptBuilder
from ..shared.schemas.architecture_schema import ArchitectureArtifact
from .base_action import LLMAction


class WriteArchitectureAction(LLMAction):
    """Architect's action: produces a structured ArchitectureArtifact."""

    name = "WriteArchitecture"
    description = "Design the system architecture: modules, API design, data models, and tech stack."
    schema_model = ArchitectureArtifact
    system_prompt = (
        "You are a Software Architect producing a system design. "
        "Respond with ONLY a single JSON object (no prose outside it) with these keys: "
        "approach (string), modules (list of objects with name/purpose/dependencies), "
        "api_design (list of objects with path/method/request/response), "
        "data_models (list of objects with name/fields), tech_stack (object mapping layer to technology)."
    )

    def __init__(self, prompt_builder: ArchitectPromptBuilder | None = None) -> None:
        """Wire the Architect prompt builder this action uses."""
        super().__init__(prompt_builder or ArchitectPromptBuilder())
