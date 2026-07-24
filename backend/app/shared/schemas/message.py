from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ..enums.stage import Stage


class AgentMessage(BaseModel):
    """A structured handoff between workflow stages (inspired by MetaGPT's Message).

    WorkflowEngine writes one of these after each approved stage; the next
    stage's WorkflowEngine.run() reads it back as predecessor context.
    """

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    role: str
    stage: Stage
    content: str
    structured: dict[str, Any] = Field(default_factory=dict)
    cause_by: str = ""
    sent_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
