from __future__ import annotations

from typing import Any

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
        "project_name (string), tagline (string), problem_statement (string), "
        "target_users (list of Persona objects with name, age, role, device_primary, specific_goal, specific_pain_point, tech_level), "
        "scale_profile (object), goals (list of strings), product_goals (list of strings), "
        "requirements (list of Requirement objects with req_id, priority, category, description, given, when, then, edge_cases), "
        "user_stories (list of UserStory objects with story_id, persona_name, story_points, priority, action, benefit, acceptance_criteria), "
        "acceptance_criteria (list of strings), non_functional_requirements (object), constraints (list of strings), "
        "out_of_scope (list of strings from Q&A explicit_non_requirements), open_questions (list of objects), "
        "success_metrics (list of strings), anything_unclear (string)."
    )

    def __init__(self, prompt_builder: ProductOwnerPromptBuilder | None = None) -> None:
        """Wire the ProductOwner prompt builder this action uses."""
        super().__init__(prompt_builder or ProductOwnerPromptBuilder())

    def _parse_structured(self, text: str) -> dict[str, Any]:
        parsed = super()._parse_structured(text)
        if parsed:
            return parsed
        return {
            "project_name": "Software Requirements Specification",
            "tagline": "System Specification",
            "problem_statement": "Deliver clear functional requirements",
            "target_users": [],
            "scale_profile": {},
            "goals": ["Deliver clear functional requirements"],
            "product_goals": ["Deliver clear functional requirements"],
            "requirements": [],
            "user_stories": [],
            "acceptance_criteria": ["All requirements met"],
            "non_functional_requirements": {},
            "constraints": [],
            "out_of_scope": [],
            "open_questions": [],
            "success_metrics": [],
            "anything_unclear": "",
        }
