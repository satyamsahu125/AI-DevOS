from __future__ import annotations

from pydantic import BaseModel, Field


class SprintTaskSchema(BaseModel):
    task_id: str = ""
    description: str = ""
    agent: str = ""
    file_paths: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    status: str = "pending"


class SprintSchema(BaseModel):
    sprint_id: str = ""
    sprint_number: int = 1
    name: str = ""
    goal: str = ""
    features: list[str] = Field(default_factory=list)
    tasks: list[SprintTaskSchema] = Field(default_factory=list)
    status: str = "planned"
    started_at: str | None = None
    completed_at: str | None = None


class SprintPlanSchema(BaseModel):
    project_id: str = ""
    total_sprints: int = 0
    sprints: list[SprintSchema] = Field(default_factory=list)
    created_at: str = ""
    rationale: str = ""
