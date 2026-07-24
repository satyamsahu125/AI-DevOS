from __future__ import annotations

from ..prompt.retro_builder import RetroPromptBuilder
from ..shared.schemas.sprint_retrospective_schema import SprintRetrospective
from .base_action import LLMAction


class WriteRetrospectiveAction(LLMAction):
    """Retro's action: produces a structured SprintRetrospective."""

    name = "WriteRetrospective"
    description = "Summarize this sprint's shipping activity and per-contributor breakdown."
    schema_model = SprintRetrospective
    system_prompt = (
        "You are running a sprint retrospective. Respond with ONLY a single JSON object (no prose outside it) "
        "with these keys: window (string), total_commits (integer), shipping_streak_days (integer), "
        "contributors (list of objects with name/commits/top_area/praise/growth_opportunity), "
        "top_wins (list of strings), things_to_improve (list of strings)."
    )

    def __init__(self, prompt_builder: RetroPromptBuilder | None = None) -> None:
        """Wire the Retro prompt builder this action uses."""
        super().__init__(prompt_builder or RetroPromptBuilder())
