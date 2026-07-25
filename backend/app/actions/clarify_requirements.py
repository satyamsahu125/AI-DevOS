from __future__ import annotations

from ..prompt.clarification_builder import ClarificationPromptBuilder
from ..shared.schemas.clarification_schema import ClarificationArtifact
from .base_action import LLMAction


class ClarifyRequirementsAction(LLMAction):
    """ClarificationAgent's action: produces a structured ClarificationArtifact."""

    name = "ClarifyRequirements"
    description = "Clarify ambiguous user requirements, ask questions, make assumptions, and enrich requirements."
    schema_model = ClarificationArtifact
    system_prompt = (
        "You are a Requirements Clarification Specialist. "
        "Respond with ONLY a single JSON object (no prose outside it) matching these keys: "
        "original_request (string), interpretations_analyzed (list of 3 strings), "
        "divergences_found (list of strings), questions_and_answers (list of objects with question, priority, answer, source), "
        "assumptions_made (list of strings), clarified_requirement (string), clarified_requirements (string), "
        "out_of_scope (list of strings), confidence_score (float 0.0-1.0), ready_for_requirements (boolean)."
    )

    def __init__(self, prompt_builder: ClarificationPromptBuilder | None = None) -> None:
        """Wire the Clarification prompt builder this action uses."""
        super().__init__(prompt_builder or ClarificationPromptBuilder())
