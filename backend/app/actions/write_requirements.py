from __future__ import annotations

import logging
from typing import Any

from ..execution.exceptions import SchemaValidationError
from ..prompt.product_owner_builder import ProductOwnerPromptBuilder
from ..shared.schemas.requirements_schema import RequirementsArtifact
from .base_action import LLMAction

logger = logging.getLogger(__name__)


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
        "scale_profile (object with auth_needed bool, database_needed bool, user_count string, infrastructure_tier string), "
        "goals (list of strings), product_goals (list of strings), "
        "requirements (list of Requirement objects with req_id, priority, category, description, given, when, then, edge_cases), "
        "user_stories (list of UserStory objects with story_id, persona_name, story_points, priority, action, benefit, acceptance_criteria), "
        "acceptance_criteria (list of strings), non_functional_requirements (object), constraints (list of strings), "
        "out_of_scope (list of strings — MUST NOT contradict scale_profile flags), open_questions (list of objects), "
        "success_metrics (list of strings), anything_unclear (string). "
        "CRITICAL: If scale_profile.auth_needed=true, do NOT include any 'No authentication' item in out_of_scope or constraints. "
        "If scale_profile.database_needed=true, do NOT include any 'No database' item in out_of_scope or constraints. "
        "The scale_profile flags are ground truth — out_of_scope must be consistent with them."
    )

    def __init__(self, prompt_builder: ProductOwnerPromptBuilder | None = None) -> None:
        """Wire the ProductOwner prompt builder this action uses."""
        super().__init__(prompt_builder or ProductOwnerPromptBuilder())

    def _parse_structured(self, text: str) -> dict[str, Any]:
        parsed = super()._parse_structured(text)
        if not parsed:
            logger.error(
                "ProductOwnerAgent: LLM output did not parse as "
                "valid JSON matching RequirementsArtifact schema. "
                "First 300 chars of response: %s",
                (text or "")[:300],
            )
            raise SchemaValidationError(
                "Requirements output could not be parsed as valid JSON. "
                "The LLM response did not match the RequirementsArtifact schema. "
                "This stage will retry with feedback. "
                f"Response preview: {(text or '')[:200]}"
            )
        # Post-parse consistency fix: remove out_of_scope items that contradict scale_profile flags.
        scale = parsed.get("scale_profile", {})
        if scale.get("auth_needed") is True:
            parsed["out_of_scope"] = [
                item for item in parsed.get("out_of_scope", [])
                if "auth" not in item.lower() and "login" not in item.lower()
                and "account" not in item.lower() and "user account" not in item.lower()
            ]
            parsed["constraints"] = [
                item for item in parsed.get("constraints", [])
                if "no auth" not in item.lower() and "no user auth" not in item.lower()
                and "no login" not in item.lower()
            ]
        if scale.get("database_needed") is True:
            parsed["out_of_scope"] = [
                item for item in parsed.get("out_of_scope", [])
                if "database" not in item.lower() and "no db" not in item.lower()
                and "server-side storage" not in item.lower()
            ]
            parsed["constraints"] = [
                item for item in parsed.get("constraints", [])
                if "no database" not in item.lower() and "no db" not in item.lower()
                and "no server-side storage" not in item.lower()
            ]
        return parsed
