from __future__ import annotations

import logging
from typing import Any

from ..execution.exceptions import SchemaValidationError
from ..prompt.architect_builder import ArchitectPromptBuilder
from ..shared.schemas.architecture_schema import ArchitectureArtifact
from .base_action import LLMAction

logger = logging.getLogger(__name__)


class WriteArchitectureAction(LLMAction):
    """Architect's action: produces a structured ArchitectureArtifact."""

    name = "WriteArchitecture"
    description = "Design the system architecture: modules, API design, data models, and tech stack."
    schema_model = ArchitectureArtifact
    system_prompt = (
        "You are a Software Architect producing a system design. "
        "Respond with ONLY a single JSON object (no prose outside it) with these keys: "
        "implementation_approach (string), approach (string), layers (list of strings), "
        "modules (list of ModuleSpec objects with name, purpose, layer, technology, dependencies, exports, files), "
        "api_endpoints (list of APIEndpoint objects with path, method, description, request_body, response_schema, auth_required, status_codes), "
        "api_design (list of APIEndpoint objects), "
        "data_models (list of DataModel objects with name, table_name, fields, relationships, indexes), "
        "tech_stack (object mapping layer to technology), deployment_notes (string), scalability_notes (string), "
        "out_of_scope (list of strings from PRD out_of_scope), anything_unclear (string)."
    )

    def __init__(self, prompt_builder: ArchitectPromptBuilder | None = None) -> None:
        """Wire the Architect prompt builder this action uses."""
        super().__init__(prompt_builder or ArchitectPromptBuilder())

    def _parse_structured(self, text: str) -> dict[str, Any]:
        """Parse LLM response into ArchitectureArtifact schema.

        Raises SchemaValidationError if parsing fails — never
        silently falls back to fake data.
        """
        parsed = super()._parse_structured(text)
        if not parsed:
            logger.error(
                "ArchitectAgent: LLM output did not parse as "
                "valid JSON matching SystemArchitecture schema. "
                "First 300 chars of response: %s",
                (text or "")[:300],
            )
            raise SchemaValidationError(
                "Architecture output could not be parsed as valid JSON. "
                "The LLM response did not match the SystemArchitecture "
                "schema. This stage will retry with feedback. "
                f"Response preview: {(text or '')[:200]}"
            )
        return parsed
