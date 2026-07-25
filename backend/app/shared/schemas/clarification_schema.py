from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ClarificationArtifact(BaseModel):
    """Structured output of the ClarificationAgent (ClarifyRequirementsAction)."""

    original_request: str = ""
    interpretations_analyzed: list[str] = Field(default_factory=list)
    divergences_found: list[str] = Field(default_factory=list)
    questions_and_answers: list[dict[str, Any]] | list[str] = Field(default_factory=list)
    questions_asked: list[str] = Field(default_factory=list)
    answers_received: list[str] = Field(default_factory=list)
    assumptions_made: list[str] = Field(default_factory=list)
    clarified_requirements: str = ""
    clarified_requirement: str = ""
    out_of_scope: list[str] = Field(default_factory=list)
    confidence_score: float = 1.0
    ready_for_requirements: bool = True
