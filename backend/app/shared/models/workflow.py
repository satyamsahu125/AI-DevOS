from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..enums.stage import Stage
from ..enums.workflow_state import WorkflowState


@dataclass(slots=True)
class Workflow:
    id: str
    project_id: str
    current_stage: Stage
    state: WorkflowState = WorkflowState.Created
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
