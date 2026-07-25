from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", "backend/app/memory/memory.db"))

_shared_tracker: "CostTracker | None" = None


def get_shared_cost_tracker() -> "CostTracker":
    """Return a process-wide default CostTracker, so unrelated callers (e.g. LLMManager and
    WorkflowEngine) that both default-construct one still observe the same in-memory
    last_call_tokens/last_call_latency -- not just the same underlying SQLite file.
    """
    global _shared_tracker
    if _shared_tracker is None:
        _shared_tracker = CostTracker()
    return _shared_tracker


@dataclass(slots=True)
class CostSummary:
    """Aggregated token/latency totals for some scope (a stage, a project, or everything)."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0


class CostTracker:
    """Records per-LLM-call token usage and latency, and aggregates it by stage/project.

    Inspired by MetaGPT's CostManager, adapted for AI DevOS: since every
    call here runs against a free local Ollama server, there is no dollar
    cost to track -- only token counts and latency -- persisted to the
    `llm_calls` SQLite table (in the same memory.db MemoryManager uses; see
    Fix 5) so it survives process restarts, as documented in
    docs/LEARNING-SYSTEM.md's ObservabilityMemory.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        """Open (creating on first run) the sqlite3 database backing the llm_calls table."""
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._ensure_schema()
        self.last_call_tokens: int = 0
        self.last_call_latency: float = 0.0

    def _ensure_schema(self) -> None:
        """Create the llm_calls table on first run."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stage TEXT,
                agent TEXT,
                project_id TEXT,
                model TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                latency_ms REAL,
                recorded_at TEXT
            )
            """
        )
        self._conn.commit()
        logger.debug("cost tracker schema ready: db=%s", self._db_path)

    def record(
        self,
        stage: str,
        agent: str,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
        latency_ms: float,
        project_id: str = "",
    ) -> None:
        """Persist one LLM call's token usage and latency, and update last_call_tokens/last_call_latency."""
        logger.debug(
            "cost record: stage=%s agent=%s model=%s prompt_tokens=%s completion_tokens=%s latency_ms=%.1f",
            stage, agent, model, prompt_tokens, completion_tokens, latency_ms,
        )
        self.last_call_tokens = int(prompt_tokens) + int(completion_tokens)
        self.last_call_latency = float(latency_ms)
        self._conn.execute(
            "INSERT INTO llm_calls "
            "(stage, agent, project_id, model, prompt_tokens, completion_tokens, latency_ms, recorded_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                stage, agent, project_id, model, int(prompt_tokens), int(completion_tokens),
                float(latency_ms), datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def get_stage_cost(self, stage: str) -> CostSummary:
        """Return the aggregated CostSummary for every call recorded under stage."""
        return self._summarize("WHERE stage = ?", (stage,))

    def get_project_cost(self, project_id: str) -> CostSummary:
        """Return the aggregated CostSummary for every call recorded under project_id."""
        return self._summarize("WHERE project_id = ?", (project_id,))

    def get_total(self) -> CostSummary:
        """Return the aggregated CostSummary across every recorded call."""
        return self._summarize("", ())

    def _summarize(self, where: str, params: tuple[Any, ...]) -> CostSummary:
        query = (
            "SELECT COUNT(*), COALESCE(SUM(prompt_tokens), 0), COALESCE(SUM(completion_tokens), 0), "
            "COALESCE(SUM(latency_ms), 0) FROM llm_calls " + where
        )
        calls, prompt_tokens, completion_tokens, total_latency_ms = self._conn.execute(query, params).fetchone()
        return CostSummary(
            calls=calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            total_latency_ms=total_latency_ms,
        )
