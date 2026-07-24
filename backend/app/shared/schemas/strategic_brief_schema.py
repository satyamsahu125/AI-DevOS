from __future__ import annotations

from pydantic import BaseModel, Field


class ScopeDecision(BaseModel):
    """One in/out scope call in a strategic brief."""

    proposal: str = ""
    effort: str = ""
    decision: str = ""
    reasoning: str = ""


class StrategicBrief(BaseModel):
    """Structured output of the StrategicReview stage (inspired by gstack's /office-hours + /plan-ceo-review)."""

    vision: str = ""
    ten_x_check: str = ""
    scope_decisions: list[ScopeDecision] = Field(default_factory=list)
    accepted_scope: list[str] = Field(default_factory=list)
    deferred_to_backlog: list[str] = Field(default_factory=list)
