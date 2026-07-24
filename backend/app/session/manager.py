from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from ..shared.enums.session_state import SessionState
from ..shared.models.stage_session import StageSession

logger = logging.getLogger(__name__)


class SessionManager:
    """Owns the lifecycle of StageSession objects for stage execution.

    Every workflow stage owns exactly one active StageSession for the
    duration of its execute -> review -> retry cycle. SessionManager is the
    only component allowed to create, update, or close a session; no other
    component may mutate session state directly.
    """

    def __init__(self) -> None:
        """Initialize an empty registry of active sessions."""
        self._sessions: dict[str, StageSession] = {}

    def create_session(self, stage: str) -> StageSession:
        """Create, register, and return a new Active StageSession for the given stage."""
        session = StageSession(
            session_id=str(uuid.uuid4()),
            stage=stage,
            state=SessionState.Active,
            created_at=datetime.now(timezone.utc),
            retry_count=0,
        )
        self._sessions[session.session_id] = session
        logger.info("session created: session_id=%s stage=%s", session.session_id, stage)
        return session

    def increment_retry(self, session: StageSession) -> StageSession:
        """Increment the retry counter on an active session after a rejected review."""
        session.retry_count += 1
        logger.info(
            "session retry incremented: session_id=%s stage=%s retry_count=%s",
            session.session_id, session.stage, session.retry_count,
        )
        return session

    def close_session(self, session: StageSession) -> StageSession:
        """Mark a session Closed and remove it from the active registry."""
        session.state = SessionState.Closed
        self._sessions.pop(session.session_id, None)
        logger.info(
            "session closed: session_id=%s stage=%s retry_count=%s",
            session.session_id, session.stage, session.retry_count,
        )
        return session

    def get_session(self, session_id: str) -> StageSession | None:
        """Return the active session for session_id, or None if it does not exist or has been closed."""
        return self._sessions.get(session_id)
