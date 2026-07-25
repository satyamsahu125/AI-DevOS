import json
import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", "backend/app/memory/memory.db"))


@dataclass(slots=True)
class SessionCheckpoint:
    """A resumable snapshot of one stage session's progress (inspired by gstack's /context-save).

    decisions_made and remaining_work map directly onto gstack's "Decisions
    Made" / "Remaining Work" checkpoint sections; failed_approaches maps
    onto gstack's "Tried: <failed approaches>" trailer (its continuous
    checkpoint mode) so a resumed session doesn't repeat a dead end.
    """

    session_id: str
    stage: str
    project_id: str
    attempt_number: int
    decisions_made: list[str] = field(default_factory=list)
    remaining_work: list[str] = field(default_factory=list)
    failed_approaches: list[str] = field(default_factory=list)
    last_artifact_summary: str = ""
    saved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CheckpointManager:
    """Persists SessionCheckpoints to SQLite so an interrupted session can be resumed.

    A checkpoint's existence means "this session is incomplete" -- it is
    saved before risky work (each LLM call) and deleted only once the
    session closes successfully, so list_incomplete() doubles as crash
    recovery: anything still there when the process starts back up was
    never cleanly finished.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Open (creating on first run) the sqlite3 database backing the session_checkpoints table."""
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the session_checkpoints table on first run."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_checkpoints (
                session_id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                project_id TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                decisions_made TEXT NOT NULL,
                remaining_work TEXT NOT NULL,
                failed_approaches TEXT NOT NULL,
                last_artifact_summary TEXT NOT NULL,
                saved_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        logger.debug("checkpoint manager schema ready: db=%s", self._db_path)

    def save(self, session_id: str, checkpoint: SessionCheckpoint) -> None:
        """Persist checkpoint under session_id, replacing any previous checkpoint for it."""
        logger.info("saving checkpoint: session_id=%s stage=%s attempt=%s", session_id, checkpoint.stage, checkpoint.attempt_number)
        self._conn.execute(
            """
            INSERT INTO session_checkpoints
                (session_id, stage, project_id, attempt_number, decisions_made,
                 remaining_work, failed_approaches, last_artifact_summary, saved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                stage = excluded.stage,
                project_id = excluded.project_id,
                attempt_number = excluded.attempt_number,
                decisions_made = excluded.decisions_made,
                remaining_work = excluded.remaining_work,
                failed_approaches = excluded.failed_approaches,
                last_artifact_summary = excluded.last_artifact_summary,
                saved_at = excluded.saved_at
            """,
            (
                session_id,
                checkpoint.stage,
                checkpoint.project_id,
                checkpoint.attempt_number,
                json.dumps(checkpoint.decisions_made),
                json.dumps(checkpoint.remaining_work),
                json.dumps(checkpoint.failed_approaches),
                checkpoint.last_artifact_summary,
                checkpoint.saved_at.isoformat(),
            ),
        )
        self._conn.commit()

    def restore(self, session_id: str) -> SessionCheckpoint | None:
        """Return the saved checkpoint for session_id, or None if none exists."""
        row = self._conn.execute(
            "SELECT session_id, stage, project_id, attempt_number, decisions_made, "
            "remaining_work, failed_approaches, last_artifact_summary, saved_at "
            "FROM session_checkpoints WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_checkpoint(row)

    def delete(self, session_id: str) -> None:
        """Remove the checkpoint for session_id, if any (called after a session closes successfully)."""
        logger.info("deleting checkpoint: session_id=%s", session_id)
        self._conn.execute("DELETE FROM session_checkpoints WHERE session_id = ?", (session_id,))
        self._conn.commit()

    def cleanup_old_checkpoints(self, days: int = 7) -> int:
        """
        Delete checkpoints older than `days` days.
        Returns count of deleted records.
        Called at kernel startup.
        """
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        cursor = self._conn.execute(
            "DELETE FROM session_checkpoints WHERE saved_at < ?",
            (cutoff.isoformat(),)
        )
        self._conn.commit()
        deleted = cursor.rowcount
        if deleted > 0:
            logger.info(
                "CheckpointManager: cleaned up %d stale checkpoints "
                "older than %d days", deleted, days
            )
        return deleted

    def list_incomplete(self) -> list[SessionCheckpoint]:
        """Return every saved checkpoint -- each one is, by definition, an incomplete session."""
        rows = self._conn.execute(
            "SELECT session_id, stage, project_id, attempt_number, decisions_made, "
            "remaining_work, failed_approaches, last_artifact_summary, saved_at "
            "FROM session_checkpoints ORDER BY saved_at DESC"
        ).fetchall()
        return [self._row_to_checkpoint(row) for row in rows]

    def _row_to_checkpoint(self, row: tuple) -> SessionCheckpoint:
        (session_id, stage, project_id, attempt_number, decisions_made,
         remaining_work, failed_approaches, last_artifact_summary, saved_at) = row
        return SessionCheckpoint(
            session_id=session_id,
            stage=stage,
            project_id=project_id,
            attempt_number=attempt_number,
            decisions_made=json.loads(decisions_made),
            remaining_work=json.loads(remaining_work),
            failed_approaches=json.loads(failed_approaches),
            last_artifact_summary=last_artifact_summary,
            saved_at=datetime.fromisoformat(saved_at),
        )
