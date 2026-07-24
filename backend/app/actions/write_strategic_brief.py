from __future__ import annotations

from ..prompt.strategic_review_builder import StrategicReviewPromptBuilder
from ..shared.schemas.strategic_brief_schema import StrategicBrief
from .base_action import LLMAction


class WriteStrategicBriefAction(LLMAction):
    """StrategicReview's action: produces a structured StrategicBrief."""

    name = "WriteStrategicBrief"
    description = "Reframe the request, run a 10x check, and make scope decisions explicit."
    schema_model = StrategicBrief
    system_prompt = (
        "You are running a strategic review. Respond with ONLY a single JSON object (no prose outside it) "
        "with these keys: vision (string), ten_x_check (string), "
        "scope_decisions (list of objects with proposal/effort/decision/reasoning), "
        "accepted_scope (list of strings), deferred_to_backlog (list of strings)."
    )

    def __init__(self, prompt_builder: StrategicReviewPromptBuilder | None = None) -> None:
        """Wire the StrategicReview prompt builder this action uses."""
        super().__init__(prompt_builder or StrategicReviewPromptBuilder())
