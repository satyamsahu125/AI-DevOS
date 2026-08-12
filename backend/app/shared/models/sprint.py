from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, field_validator


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rationale: str = ""  # why split this way; optional — LLMs often omit it
    stale: bool = False  # True when a requirement change has invalidated this plan
    requirement_version_id: str | None = None  # version that produced this plan

    @field_validator("created_at", mode="before")
    @classmethod
    def _ensure_utc(cls, v: object) -> datetime:
        """Coerce naive datetimes to UTC; reject empty strings early."""
        if v is None or v == "":
            return datetime.now(timezone.utc)
        if isinstance(v, str):
            dt = datetime.fromisoformat(v)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v  # type: ignore[return-value]


class SprintResult(BaseModel):
    all_sprints_complete: bool = False
    sprint_complete: bool = False
    success: bool = True
    message: str = ""
