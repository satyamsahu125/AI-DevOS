from __future__ import annotations

from pydantic import BaseModel, Field


class DomainBrief(BaseModel):
    """Structured domain knowledge produced by DomainResearcherAgent.

    Used by ClarificationAgent to ask domain-relevant questions and
    avoid asking obvious ones. Stored as a stage artifact so downstream
    agents can reference it.
    """

    domain: str = ""
    complexity: str = "medium"          # "low" | "medium" | "high"
    standard_modules: list[str] = Field(default_factory=list)
    standard_actors: list[str] = Field(default_factory=list)
    standard_integrations: list[str] = Field(default_factory=list)
    common_pitfalls: list[str] = Field(default_factory=list)
    regulatory_concerns: list[str] = Field(default_factory=list)
    questions_to_ask: list[str] = Field(default_factory=list)
    questions_not_to_ask: list[str] = Field(default_factory=list)
    comparable_products: list[str] = Field(default_factory=list)
    anything_unusual: str = ""
