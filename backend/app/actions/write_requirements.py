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

    def _parse_structured(self, text: str) -> dict[str, Any]:
        parsed = super()._parse_structured(text)
        if parsed:
            return parsed
        lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
        bullets = [line.lstrip("-*0123456789. ").strip() for line in lines if line.startswith(("-", "*")) or (line[0].isdigit() and "." in line[:3])]
        return {
            "project_name": "Software Requirements Specification",
            "goals": [b for b in bullets if len(b) > 5][:8] or ["Implement requested product features"],
            "user_stories": [b for b in bullets if "as a" in b.lower() or "user" in b.lower() or "want" in b.lower()] or ["As a user, I want full functionality"],
            "acceptance_criteria": [b for b in bullets if "given" in b.lower() or "when" in b.lower() or "then" in b.lower() or "req-" in b.lower()] or ["All acceptance criteria met"],
            "constraints": [b for b in bullets if "must" in b.lower() or "sec" in b.lower() or "perf" in b.lower()] or ["Standard system constraints"],
            "out_of_scope": [b for b in bullets if "out" in b.lower() or "defer" in b.lower()] or ["Future roadmap enhancements"],
        }
