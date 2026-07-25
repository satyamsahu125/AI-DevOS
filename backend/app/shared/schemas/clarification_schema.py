from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class QuestionAnswer(BaseModel):
    question: str = ""
    category: str = ""
    priority: str = ""
    answer: str = ""
    source: str = ""
    confidence: str = ""


class ScaleProfile(BaseModel):
    user_count: str = "under_100"
    database_needed: bool = False
    auth_needed: bool = False
    infrastructure_tier: str = "static_frontend_only"
    peak_requests_per_second: int | None = None
    data_volume: str = "none"
    cache_needed: bool = False
    cdn_needed: bool = False


class ClarificationArtifact(BaseModel):
    """Structured output of the ClarificationAgent (ClarifyRequirementsAction)."""

    original_request: str = ""
    interpretations_analyzed: list[str] = Field(default_factory=list)
    divergences_found: list[str] = Field(default_factory=list)
    questions_and_answers: list[QuestionAnswer] | list[dict[str, Any]] | list[str] = Field(default_factory=list)
    questions_asked: list[str] = Field(default_factory=list)
    answers_received: list[str] = Field(default_factory=list)
    assumptions_made: list[str] = Field(default_factory=list)
    explicit_non_requirements: list[str] = Field(default_factory=list)
    clarified_requirement: str = ""
    clarified_requirements: str = ""
    scale_profile: ScaleProfile = Field(
        default_factory=lambda: ScaleProfile(
            user_count="under_100",
            database_needed=False,
            auth_needed=False,
            infrastructure_tier="static_frontend_only",
        )
    )
    confidence_score: float = 1.0
    ready_for_requirements: bool = True
