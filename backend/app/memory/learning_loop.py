from __future__ import annotations

import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .knowledge_memory import KnowledgeMemory

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(os.getenv("LEARNING_DB_PATH", "backend/app/memory/learning.db"))


@dataclass(slots=True)
class Trajectory:
    """A single agent stage run: what it was asked to do, what it produced, and how it went.

    Inspired by ruflo's neural Trajectory (research/ruflo/v3/@claude-flow/neural),
    simplified to just what's needed for retrieval and stats -- no RL
    algorithms (PPO/DQN/etc. are explicitly out of scope here).
    """

    stage: str
    task_description: str
    artifact_summary: str
    retry_count: int
    approved: bool
    reviewer_feedback: str
    agent_model: str
    tokens_used: int
    latency_ms: float
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    project_id: str = ""


@dataclass(slots=True)
class AgentPerformance:
    """Aggregated stats for every trajectory recorded under one stage."""

    total: int = 0
    success_rate: float = 0.0
    avg_retries: float = 0.0
    avg_tokens: float = 0.0
    avg_latency: float = 0.0


class LearningLoop:
    """Records every stage run and surfaces what worked (and what didn't) to future runs.

    Inspired by ruflo's SONA/ReasoningBank (research/ruflo/v3/@claude-flow/neural),
    simplified to trajectory recording and retrieval only. Every trajectory
    (approved or rejected) is logged to SQLite for stats; only approved ones
    are embedded into KnowledgeMemory, so semantic search only ever surfaces
    things that actually worked.
    """

    def __init__(self, knowledge_memory: KnowledgeMemory | None = None, db_path: Path | None = None) -> None:
        """Wire the KnowledgeMemory (for approved-trajectory vectors) and the trajectory-log SQLite database."""
        self._lock = threading.RLock()
        self.knowledge_memory = knowledge_memory or KnowledgeMemory()
        self._db_path = Path(db_path) if db_path is not None else _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._ensure_schema()
        logger.debug("learning loop ready: db=%s", self._db_path)

    def _ensure_schema(self) -> None:
        """Create the trajectories table on first run."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trajectories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL DEFAULT '',
                stage TEXT NOT NULL,
                task_description TEXT NOT NULL,
                artifact_summary TEXT NOT NULL,
                retry_count INTEGER NOT NULL,
                approved INTEGER NOT NULL,
                reviewer_feedback TEXT NOT NULL,
                agent_model TEXT NOT NULL,
                tokens_used INTEGER NOT NULL,
                latency_ms REAL NOT NULL,
                recorded_at TEXT NOT NULL
            )
            """
        )
        cursor = self._conn.execute("PRAGMA table_info(trajectories)")
        columns = [row[1] for row in cursor.fetchall()]
        if "project_id" not in columns:
            self._conn.execute("ALTER TABLE trajectories ADD COLUMN project_id TEXT NOT NULL DEFAULT ''")
        self._conn.commit()

    def record_trajectory(self, trajectory: Trajectory, project_id: str = "") -> None:
        """Log trajectory to SQLite (always), and embed it into KnowledgeMemory only if approved."""
        with self._lock:
            eff_project_id = project_id or getattr(trajectory, "project_id", "") or ""
            logger.info(
                "recording trajectory: project_id=%s stage=%s approved=%s retries=%s",
                eff_project_id, trajectory.stage, trajectory.approved, trajectory.retry_count,
            )
            cursor = self._conn.execute(
                """
                INSERT INTO trajectories
                    (project_id, stage, task_description, artifact_summary, retry_count, approved,
                     reviewer_feedback, agent_model, tokens_used, latency_ms, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eff_project_id,
                    trajectory.stage,
                    trajectory.task_description,
                    trajectory.artifact_summary,
                    trajectory.retry_count,
                    int(trajectory.approved),
                    trajectory.reviewer_feedback,
                    trajectory.agent_model,
                    trajectory.tokens_used,
                    trajectory.latency_ms,
                    trajectory.recorded_at.isoformat(),
                ),
            )
            self._conn.commit()
            row_id = cursor.lastrowid

            if trajectory.approved:
                key = f"trajectory:{trajectory.stage}:{row_id}"
                value = f"Task: {trajectory.task_description}\nOutcome: {trajectory.artifact_summary}"
                category = self._category_for(trajectory.stage, eff_project_id)
                self.knowledge_memory.store(key, value, category=category, source="learning_loop")
                logger.debug("approved trajectory embedded into knowledge memory: key=%s category=%s", key, category)

    def get_project_trajectories(self, project_id: str, stage: str | None = None) -> list[dict]:
        """Query trajectories for a specific project."""
        with self._lock:
            if stage:
                rows = self._conn.execute(
                    """
                    SELECT id, project_id, stage, task_description, artifact_summary,
                           retry_count, approved, reviewer_feedback, agent_model,
                           tokens_used, latency_ms, recorded_at
                    FROM trajectories WHERE project_id = ? AND stage = ?
                    ORDER BY id ASC
                    """,
                    (project_id, stage),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT id, project_id, stage, task_description, artifact_summary,
                           retry_count, approved, reviewer_feedback, agent_model,
                           tokens_used, latency_ms, recorded_at
                    FROM trajectories WHERE project_id = ?
                    ORDER BY id ASC
                    """,
                    (project_id,),
                ).fetchall()
            return [
                {
                    "id": row[0],
                    "project_id": row[1],
                    "stage": row[2],
                    "task_description": row[3],
                    "artifact_summary": row[4],
                    "retry_count": row[5],
                    "approved": bool(row[6]),
                    "reviewer_feedback": row[7],
                    "agent_model": row[8],
                    "tokens_used": row[9],
                    "latency_ms": row[10],
                    "recorded_at": row[11],
                }
                for row in rows
            ]

    def get_relevant_patterns(self, task: str, stage: str, project_id: str = "", top_k: int = 3) -> list[str]:
        """Semantic-search past approved trajectories for stage, returning their text (used by ContextManager).

        When project_id is given, only patterns recorded under that same
        project_id/stage are considered -- otherwise (the default, kept for
        backward compatibility) the search spans every project's trajectories
        for stage, which is how this looked before project isolation and is
        what existing callers/tests that don't pass project_id still get.
        """
        logger.debug("get_relevant_patterns: stage=%s project_id=%s top_k=%s", stage, project_id, top_k)
        category = self._category_for(stage, project_id)
        results = self.knowledge_memory.search(task, top_k=top_k, category_filter=category)
        return [result.value for result in results]

    @staticmethod
    def _category_for(stage: str, project_id: str) -> str:
        """Build the KnowledgeMemory category key: project-scoped when project_id is given, plain stage otherwise."""
        return f"{project_id}:{stage}" if project_id else stage

    def count_all_trajectories(self) -> int:
        """Return the total number of trajectories recorded across every project/stage.

        The trajectories table has no project_id column (trajectories are
        attributed to a project only via the in-process Trajectory.project_id
        field used to scope KnowledgeMemory pattern search, see
        get_relevant_patterns) so this count is necessarily global, not
        per-project.
        """
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM trajectories").fetchone()
            return int(row[0]) if row else 0

    def get_agent_performance(self, stage: str) -> AgentPerformance:
        """Aggregate total/success_rate/avg_retries/avg_tokens/avg_latency for every trajectory under stage."""
        with self._lock:
            logger.debug("get_agent_performance: stage=%s", stage)
            row = self._conn.execute(
                """
                SELECT COUNT(*), COALESCE(AVG(approved), 0), COALESCE(AVG(retry_count), 0),
                       COALESCE(AVG(tokens_used), 0), COALESCE(AVG(latency_ms), 0)
                FROM trajectories WHERE stage = ?
                """,
                (stage,),
            ).fetchone()
            total, success_rate, avg_retries, avg_tokens, avg_latency = row
            return AgentPerformance(
                total=total,
                success_rate=success_rate,
                avg_retries=avg_retries,
                avg_tokens=avg_tokens,
                avg_latency=avg_latency,
            )

    def get_failure_patterns(self, stage: str, limit: int = 5) -> list[str]:
        """Return the most recent distinct reviewer_feedback strings from rejected trajectories under stage."""
        with self._lock:
            logger.debug("get_failure_patterns: stage=%s", stage)
            rows = self._conn.execute(
                """
                SELECT DISTINCT reviewer_feedback FROM trajectories
                WHERE stage = ? AND approved = 0 AND reviewer_feedback != ''
                ORDER BY recorded_at DESC LIMIT ?
                """,
                (stage, limit),
            ).fetchall()
            return [row[0] for row in rows]
