from __future__ import annotations

from pydantic import BaseModel, Field


class RequirementsArtifact(BaseModel):
    """Structured output of the ProductOwner stage (inspired by MetaGPT's WritePRD)."""

    project_name: str = ""
    goals: list[str] = Field(default_factory=list)
    user_stories: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
