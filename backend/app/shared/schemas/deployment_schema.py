from __future__ import annotations

from pydantic import BaseModel, Field


class DeploymentStep(BaseModel):
    """One step in a deployment plan."""

    name: str = ""
    command: str = ""
    description: str = ""


class DeploymentArtifact(BaseModel):
    """Structured output of the DevOps stage.

    Not part of MetaGPT's action set (it has no DevOps role) -- added here
    so DevOps fits the same structured-output pattern as the other five
    agents, since AI DevOS has a DevOps stage MetaGPT does not.
    """

    steps: list[DeploymentStep] = Field(default_factory=list)
    environment: dict[str, str] = Field(default_factory=dict)
    rollback_plan: str = ""
