from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field

from ..enums.project_state import ProjectState


class PipelineResult(BaseModel):
    project_id: str
    state: ProjectState
    success: bool = False
    message: str = ""
    requires_user_action: bool = False
    action_needed: str | None = None
    completed_stages: list[str] = Field(default_factory=list)
    current_sprint: int | None = None
    total_sprints: int | None = None
    failed_stage: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    stopped: bool = False
