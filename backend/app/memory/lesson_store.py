import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Phase 6 MIGRATE: anchored default — parents[2] from backend/app/memory/ = backend/.
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_DB_PATH = Path(os.getenv("LESSONS_DB", str(_DATA_DIR / "lessons.sqlite")))


@dataclass(slots=True)
class Lesson:
    """One human-readable lesson learned from a stage's approval (inspired by gstack's /learn skill)."""

    lesson_id: str
    stage: str
    project_id: str
    what_worked: str
    what_failed: str
    reviewer_said: str
    retry_count_when_learned: int
    created_at: datetime


class LessonStore:
    """Stores human-readable lessons (not vectors) that complement LearningLoop's semantic memory.

    Inspired by gstack's /learn skill: a curated, human-readable knowledge
    store distinct from vector-based semantic recall. LearningLoop (see
    learning_loop.py) answers "what's semantically similar to this task?";
    LessonStore answers "what have we explicitly learned for this stage?" --
    meant to be read directly, not searched by embedding similarity.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Open (creating on first run) the sqlite3 database backing the lessons table."""
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the lessons table on first run."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lessons (
                lesson_id TEXT PRIMARY KEY,
                stage TEXT NOT NULL,
                project_id TEXT NOT NULL,
                what_worked TEXT NOT NULL,
                what_failed TEXT NOT NULL,
                reviewer_said TEXT NOT NULL,
                retry_count_when_learned INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()
        logger.debug("lesson store schema ready: db=%s", self._db_path)

    def record(
        self,
        stage: str,
        project_id: str,
        what_worked: str = "",
        what_failed: str = "",
        reviewer_said: str = "",
        retry_count: int = 0,
    ) -> None:
        """Convenience wrapper around add_lesson with auto-generated lesson_id.

        Called by MemoryOrchestrator.record_rejection() so callers don't need
        to construct a Lesson object directly.
        """
        lesson = Lesson(
            lesson_id=str(uuid.uuid4()),
            stage=stage,
            project_id=project_id,
            what_worked=what_worked,
            what_failed=what_failed,
            reviewer_said=reviewer_said,
            retry_count_when_learned=retry_count,
            created_at=datetime.now(timezone.utc),
        )
        self.add_lesson(lesson)

    def add_lesson(self, lesson: Lesson) -> None:
        """Persist lesson."""
        logger.info("adding lesson: stage=%s project_id=%s lesson_id=%s", lesson.stage, lesson.project_id, lesson.lesson_id)
        self._conn.execute(
            """
            INSERT INTO lessons
                (lesson_id, stage, project_id, what_worked, what_failed, reviewer_said,
                 retry_count_when_learned, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lesson.lesson_id, lesson.stage, lesson.project_id, lesson.what_worked,
                lesson.what_failed, lesson.reviewer_said, lesson.retry_count_when_learned,
                lesson.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_lessons(self, stage: str, project_id: str, limit: int = 5) -> list[Lesson]:
        """Return the most recent lessons for this exact stage/project_id."""
        logger.debug("get_lessons: stage=%s project_id=%s limit=%s", stage, project_id, limit)
        rows = self._conn.execute(
            """
            SELECT lesson_id, stage, project_id, what_worked, what_failed, reviewer_said,
                   retry_count_when_learned, created_at
            FROM lessons WHERE stage = ? AND project_id = ? ORDER BY created_at DESC LIMIT ?
            """,
            (stage, project_id, limit),
        ).fetchall()
        return [self._row_to_lesson(row) for row in rows]

    def count_for_project(self, project_id: str) -> int:
        """Return how many lessons have been recorded (across every stage) for project_id."""
        row = self._conn.execute("SELECT COUNT(*) FROM lessons WHERE project_id = ?", (project_id,)).fetchone()
        return int(row[0]) if row else 0

    def get_all_lessons(self, stage: str, limit: int = 10) -> list[Lesson]:
        """Return the most recent lessons for this stage across every project."""
        logger.debug("get_all_lessons: stage=%s limit=%s", stage, limit)
        rows = self._conn.execute(
            """
            SELECT lesson_id, stage, project_id, what_worked, what_failed, reviewer_said,
                   retry_count_when_learned, created_at
            FROM lessons WHERE stage = ? ORDER BY created_at DESC LIMIT ?
            """,
            (stage, limit),
        ).fetchall()
        return [self._row_to_lesson(row) for row in rows]

    def prune_old_lessons(self, older_than_days: int = 90) -> int:
        """Delete lessons older than older_than_days; returns how many were removed."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat()
        cursor = self._conn.execute("DELETE FROM lessons WHERE created_at < ?", (cutoff,))
        self._conn.commit()
        removed = cursor.rowcount if cursor.rowcount is not None and cursor.rowcount > 0 else 0
        logger.info("pruned lessons: older_than_days=%s removed=%s", older_than_days, removed)
        return removed

    def export_lessons(self, stage: str) -> str:
        """Render every lesson for stage (across all projects) as a markdown document."""
        lessons = self.get_all_lessons(stage, limit=1_000_000)
        lines = [f"## Lessons: {stage}", ""]
        if not lessons:
            lines.append("_No lessons recorded yet._")
        for lesson in lessons:
            lines.append(f"- **Project**: {lesson.project_id}")
            lines.append(f"  **What worked**: {lesson.what_worked}")
            lines.append(f"  **What failed**: {lesson.what_failed}")
            lines.append(f"  **Reviewer said**: {lesson.reviewer_said}")
            lines.append(f"  _(learned after {lesson.retry_count_when_learned} retries, {lesson.created_at.isoformat()})_")
            lines.append("")
        return "\n".join(lines)

    def _row_to_lesson(self, row: tuple) -> Lesson:
        (lesson_id, stage, project_id, what_worked, what_failed, reviewer_said,
         retry_count_when_learned, created_at) = row
        try:
            dt = datetime.fromisoformat(created_at)
        except Exception:
            dt = datetime.now(timezone.utc)
        return Lesson(
            lesson_id=lesson_id,
            stage=stage,
            project_id=project_id,
            what_worked=what_worked,
            what_failed=what_failed,
            reviewer_said=reviewer_said,
            retry_count_when_learned=retry_count_when_learned,
            created_at=dt,
        )


def new_lesson_id() -> str:
    """Generate a fresh lesson_id (a UUID4 string)."""
    return str(uuid.uuid4())
