from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..enums.session_state import SessionState


@dataclass
class StageSession:
    session_id: str
    stage: str
    state: SessionState = SessionState.Active
    created_at: datetime = field(default_factory=datetime.utcnow)
    retry_count: int = 0
