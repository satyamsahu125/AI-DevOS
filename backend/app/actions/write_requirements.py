from __future__ import annotations

from ..prompt.product_owner_builder import ProductOwnerPromptBuilder
from ..shared.schemas.requirements_schema import RequirementsArtifact
from .base_action import LLMAction


class WriteRequirementsAction(LLMAction):
    """ProductOwner's action: produces a structured RequirementsArtifact."""

    name = "WriteRequirements"
    description = "Draft goals, user stories, acceptance criteria, and constraints for the project."
    schema_model = RequirementsArtifact
    system_prompt = (
        "You are a Product Owner producing a requirements specification. "
        "Respond with ONLY a single JSON object (no prose outside it) with these keys: "
        "project_name (string), goals (list of strings), user_stories (list of strings), "
        "acceptance_criteria (list of strings), constraints (list of strings), out_of_scope (list of strings)."
    )

    def __init__(self, prompt_builder: ProductOwnerPromptBuilder | None = None) -> None:
        """Wire the ProductOwner prompt builder this action uses."""
        super().__init__(prompt_builder or ProductOwnerPromptBuilder())
