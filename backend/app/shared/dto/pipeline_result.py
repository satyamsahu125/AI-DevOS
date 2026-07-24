from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class PipelineResult:
    """Result of running the full multi-stage pipeline for one project (WorkflowManager.run())."""

    project_id: str
    completed_stages: list[str]
    failed_stage: str | None
    success: bool
    message: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    stopped: bool = False
