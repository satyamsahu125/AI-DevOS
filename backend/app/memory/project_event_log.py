import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", "backend/app/memory/memory.db"))


@dataclass(slots=True)
class ProjectEvent:
    """One real, timestamped build-progress event for a project (e.g. "Architect: attempt 2 rejected")."""

    id: int
    project_id: str
    stage: str
    level: str
    message: str
    created_at: datetime


class ProjectEventLog:
    """Persists real build-progress events so a frontend can show a genuine live log feed,
    not just a synthesized diff of periodic status polls.

    Backed by the same shared memory.db every other lightweight tracker in this app uses
    (MemoryManager/ArtifactManager/CheckpointManager/CostTracker/SafetyPolicy). WorkflowEngine
    records one event at each real milestone (stage started, each attempt executing, each
    rejection with its feedback, approval, final failure) -- get_events()'s since_id parameter
    lets a poller fetch only what's new since its last request, the same pattern log-tailing
    UIs use everywhere.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def record(self, project_id: str, stage: str, message: str, level: str = "info") -> None:
        """Persist one real build event for project_id."""
        if not project_id:
            return
        self._conn.execute(
            "INSERT INTO project_events (project_id, stage, level, message, created_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, stage, level, message, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        logger.debug("project event recorded: project_id=%s stage=%s message=%s", project_id, stage, message)

    def get_events(self, project_id: str, since_id: int = 0, limit: int = 500) -> list[ProjectEvent]:
        """Return project_id's events with id > since_id, oldest first (poll with the last
        returned event's id as the next call's since_id to fetch only what's new)."""
        rows = self._conn.execute(
            "SELECT id, project_id, stage, level, message, created_at FROM project_events "
            "WHERE project_id = ? AND id > ? ORDER BY id ASC LIMIT ?",
            (project_id, since_id, limit),
        ).fetchall()
        return [
            ProjectEvent(id=row[0], project_id=row[1], stage=row[2], level=row[3], message=row[4], created_at=datetime.fromisoformat(row[5]))
            for row in rows
        ]
