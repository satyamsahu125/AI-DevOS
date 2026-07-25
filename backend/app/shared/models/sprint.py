from __future__ import annotations

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class SprintStatus(str, Enum):
    PLANNED     = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETE    = "complete"
    FAILED      = "failed"


class SprintTask(BaseModel):
    task_id: str           # UUID
    description: str       # what to build
    agent: str             # which agent handles this
    file_paths: list[str] = Field(default_factory=list)  # files this task produces
    depends_on: list[str] = Field(default_factory=list)  # task_ids this task needs first
    status: str = "pending"


class Sprint(BaseModel):
    sprint_id: str         # UUID
    sprint_number: int     # 1, 2, 3...
    name: str              # "Sprint 1: User Authentication"
    goal: str              # what this sprint delivers
    features: list[str] = Field(default_factory=list)    # user stories in this sprint
    tasks: list[SprintTask] = Field(default_factory=list) # ordered tasks for agents
    status: SprintStatus = SprintStatus.PLANNED
    started_at: datetime | None = None
    completed_at: datetime | None = None


class SprintPlan(BaseModel):
    project_id: str
    total_sprints: int
    sprints: list[Sprint] = Field(default_factory=list)
    created_at: datetime
    rationale: str  # why split this way


class SprintResult(BaseModel):
    all_sprints_complete: bool = False
    sprint_complete: bool = False
    success: bool = True
    message: str = ""
