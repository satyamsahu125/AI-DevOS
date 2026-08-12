"""CheckpointMiddleware — crash-recovery checkpoint lifecycle.

Single responsibility: save a checkpoint before each LLM attempt, delete
it on clean exit. A checkpoint left behind after process death marks that
session as recoverable.
"""
from __future__ import annotations

import logging
from typing import Any

from ...session.checkpoint import SessionCheckpoint

logger = logging.getLogger(__name__)


class CheckpointMiddleware:
    """Saves and deletes session checkpoints around each stage attempt.

    Parameters
    ----------
    checkpoint_manager:
        Persists SessionCheckpoint objects; exposes save(session_id, cp),
        delete(session_id), and list_incomplete() → list[SessionCheckpoint].
    """

    def __init__(self, checkpoint_manager: Any) -> None:
        self.checkpoint_manager = checkpoint_manager

    def report_incomplete(self) -> None:
        """Log any checkpoints left behind by a previous crashed run."""
        try:
            incomplete = self.checkpoint_manager.list_incomplete()
            if incomplete:
                logger.warning(
                    "found %d incomplete session(s) from a previous run: %s",
                    len(incomplete),
                    [(c.session_id, c.stage, c.attempt_number) for c in incomplete],
                )
        except Exception as exc:
            logger.debug("CheckpointMiddleware.report_incomplete failed: %s", exc)

    def save(
        self,
        session_id: str,
        stage_name: str,
        project_id: str,
        attempt: int,
        failed_approaches: list[str],
        last_artifact_summary: str,
    ) -> None:
        """Save a checkpoint before the next LLM call."""
        try:
            cp = SessionCheckpoint(
                session_id=session_id,
                stage=stage_name,
                project_id=project_id,
                attempt_number=attempt,
                failed_approaches=list(failed_approaches),
                last_artifact_summary=last_artifact_summary,
            )
            self.checkpoint_manager.save(session_id, cp)
        except Exception as exc:
            logger.debug("CheckpointMiddleware.save failed (non-fatal): %s", exc)

    def delete(self, session_id: str) -> None:
        """Delete checkpoint on clean exit (approval or final failure)."""
        try:
            self.checkpoint_manager.delete(session_id)
        except Exception as exc:
            logger.debug("CheckpointMiddleware.delete failed (non-fatal): %s", exc)
