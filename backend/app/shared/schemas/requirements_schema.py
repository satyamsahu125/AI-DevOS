from __future__ import annotations

from typing import Any, Union
from pydantic import BaseModel, Field, field_validator


class Persona(BaseModel):
    name: str = ""
    age: int = 30
    role: str = ""
    device_primary: str = ""
    specific_goal: str = ""
    specific_pain_point: str = ""
    tech_level: str = ""


class Requirement(BaseModel):
    req_id: str = ""
    priority: str = "MUST"
    category: str = ""
    description: str = ""
    given: str = ""
    when: str = ""
    then: str = ""
    # LLMs commonly send a string instead of a list here — coerce to list.
    edge_cases: list[str] = Field(default_factory=list)
    non_functional: str | None = None

    @field_validator("edge_cases", mode="before")
    @classmethod
    def coerce_edge_cases(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return [str(item) for item in v]
        return []


class UserStory(BaseModel):
    story_id: str = ""
    persona_name: str = ""
    story_points: int = 1
    priority: str = "HIGH"
    action: str = ""
    benefit: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def coerce_acceptance_criteria(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return [str(item) for item in v]
        return []


class RequirementsArtifact(BaseModel):
    """Structured output of the ProductOwner stage."""

    project_name: str = ""
    tagline: str = ""
    problem_statement: str = ""
    target_users: list[Persona] | list[str] = Field(default_factory=list)
    scale_profile: dict[str, Any] = Field(default_factory=dict)
    goals: list[str] = Field(default_factory=list)
    product_goals: list[str] = Field(default_factory=list)
    requirements: list[Requirement] | list[str] = Field(default_factory=list)
    user_stories: list[UserStory] | list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    # LLMs send nested dicts here (e.g. "performance": {...}), not just str values.
    non_functional_requirements: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    open_questions: list[dict[str, Any]] | list[str] = Field(default_factory=list)
    success_metrics: list[str] = Field(default_factory=list)
    anything_unclear: str = ""


ProductRequirements = RequirementsArtifact
