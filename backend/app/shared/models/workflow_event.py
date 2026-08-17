from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid


@dataclass(slots=True)
class WorkflowEvent:
    """A persisted workflow execution event for event sourcing."""

    workflow_id: str
    event_type: str
    actor: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str | None = None
    stage: str | None = None
    artifact_id: str | None = None
    payload: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))