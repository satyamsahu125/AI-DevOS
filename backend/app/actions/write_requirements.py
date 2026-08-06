from __future__ import annotations

import logging
import re
from typing import Any

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
        super().__init__(prompt_builder or ProductOwnerPromptBuilder())

    def _parse_structured(self, text: str) -> dict[str, Any]:
        parsed = super()._parse_structured(text)

        if not parsed:
            # Schema parse failed (common with small/local models).
            # Build a minimal valid artifact from the raw text so the pipeline
            # can continue rather than hard-failing this stage.
            logger.warning(
                "WriteRequirements: LLM output did not match RequirementsArtifact schema. "
                "Using minimal fallback artifact. First 300 chars: %s",
                (text or "")[:300],
            )
            parsed = self._build_fallback_artifact(text)

        return self._fix_scale_profile_consistency(parsed)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _build_fallback_artifact(raw_text: str) -> dict[str, Any]:
        """Construct a minimal RequirementsArtifact from unstructured LLM text.

        Extracts whatever facts are readable and fills the rest with empty defaults.
        All fields have Pydantic defaults so an empty dict is also valid, but
        populating project_name and problem_statement helps downstream agents.
        """
        text = raw_text or ""

        # Try to pull a project name from "project_name": "..." in the raw text
        project_name = ""
        m = re.search(r'"project_name"\s*:\s*"([^"]{1,120})"', text)
        if m:
            project_name = m.group(1)

        # Use first 500 chars of raw text as problem_statement fallback
        problem_statement = text[:500].strip() if text else ""

        # Attempt to collect goals and requirements as plain strings if visible
        goals: list[str] = []
        for m in re.finditer(r'"(?:goal|description)"\s*:\s*"([^"]{5,200})"', text):
            goals.append(m.group(1))

        artifact = RequirementsArtifact(
            project_name=project_name,
            problem_statement=problem_statement,
            goals=goals[:10],
            anything_unclear="Requirements could not be fully structured — raw LLM output was stored as problem_statement.",
        )
        return artifact.model_dump(mode="json")

    @staticmethod
    def _fix_scale_profile_consistency(parsed: dict[str, Any]) -> dict[str, Any]:
        """Remove out_of_scope / constraints entries that contradict scale_profile flags."""
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
