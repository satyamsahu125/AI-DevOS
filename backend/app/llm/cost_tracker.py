from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# Phase 6 MIGRATE: anchored default — parents[2] from backend/app/llm/ = backend/.
# Note: when wired via kernel/container.py, CostTracker receives an explicit absolute
# path (data_dir / "costs.db"). This default is only used if constructed standalone.
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", str(_DATA_DIR / "costs.db")))

_shared_tracker: CostTracker | None = None


def get_shared_cost_tracker() -> CostTracker:
    """Return a process-wide default CostTracker."""
    global _shared_tracker
    if _shared_tracker is None:
        _shared_tracker = CostTracker()
    return _shared_tracker


@dataclass
class LLMCall:
    call_id: str
    project_id: str
    stage: str
    provider: str  # "ollama" | "claude" | "gemini" | "bedrock"
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    success: bool
    error: str | None
    called_at: str


@dataclass
class StageCostSummary:
    stage: str
    llm_calls: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    avg_latency_ms: float
    total_latency_ms: float
    success_rate: float
    retries: int


@dataclass
class ProjectCostSummary:
    project_id: str
    total_llm_calls: int
    total_tokens: int
    total_latency_seconds: float
    stages: list[StageCostSummary]
    most_expensive_stage: str
    slowest_stage: str
    estimated_cost_usd: float


@dataclass(slots=True)
class CostSummary:
    """Aggregated token/latency totals for legacy callers."""

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0


# Update this when pricing changes so engineers know how stale the numbers are.
PRICING_LAST_UPDATED = "2026-07-28"

TOKEN_COST_PER_1K = {
    # Ollama local — effectively free
    "qwen2.5-coder:7b": {"input": 0.0, "output": 0.0},
    "qwen2.5-coder:14b": {"input": 0.0, "output": 0.0},
    "qwen3:8b": {"input": 0.0, "output": 0.0},
    "deepseek-r1:14b": {"input": 0.0, "output": 0.0},
    # Anthropic Claude (Messages API, per 1K tokens, USD — July 2026)
    "claude-haiku-4-5": {"input": 0.0008, "output": 0.004},
    "claude-haiku-4-5-20251001": {"input": 0.0008, "output": 0.004},
    "claude-sonnet-4-5": {"input": 0.003, "output": 0.015},
    "claude-opus-4-5": {"input": 0.015, "output": 0.075},
    "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
    "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
    # Legacy Bedrock model names (kept for backwards compat)
    "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
    "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "claude-opus-4": {"input": 0.015, "output": 0.075},
    # Google Gemini (per 1K tokens, USD — July 2026)
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
    "gemini-2.0-flash-lite": {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
    "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
}


class CostTracker:
    """Records every LLM call with token counts and latency.

    Stores in SQLite. Powers the Metrics tab in the UI.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._init_db()
        self.last_call_tokens: int = 0
        self.last_call_latency: float = 0.0
        logger.info("CostTracker initialized at %s", self._db_path)

    def _init_db(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_calls (
                call_id          TEXT PRIMARY KEY,
                project_id       TEXT NOT NULL,
                stage            TEXT NOT NULL,
                agent            TEXT DEFAULT '',
                provider         TEXT NOT NULL,
                model            TEXT NOT NULL,
                prompt_tokens    INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens     INTEGER DEFAULT 0,
                latency_ms       REAL DEFAULT 0,
                success          INTEGER DEFAULT 1,
                error            TEXT,
                called_at        TEXT NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_project ON llm_calls(project_id)")
        existing_cols = {
            r[1] for r in self._conn.execute("PRAGMA table_info(llm_calls)").fetchall()
        }
        needed_cols = {
            "call_id": "TEXT DEFAULT ''",
            "provider": "TEXT DEFAULT 'ollama'",
            "total_tokens": "INTEGER DEFAULT 0",
            "success": "INTEGER DEFAULT 1",
            "error": "TEXT",
            "called_at": "TEXT DEFAULT ''",
        }
        for col, col_def in needed_cols.items():
            if col not in existing_cols:
                try:
                    self._conn.execute(f"ALTER TABLE llm_calls ADD COLUMN {col} {col_def}")
                except Exception:
                    pass
        self._conn.commit()

    def record(
        self,
        stage: str = "",
        agent: str = "",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        model: str = "",
        latency_ms: float = 0.0,
        project_id: str = "",
        provider: str = "ollama",
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Record one LLM call."""
        call_id = str(uuid4())
        total = prompt_tokens + completion_tokens
        self.last_call_tokens = total
        self.last_call_latency = float(latency_ms)

        self._conn.execute(
            """
            INSERT INTO llm_calls
            (call_id, project_id, stage, agent, provider, model, prompt_tokens, completion_tokens, total_tokens, latency_ms, success, error, called_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                call_id,
                project_id or "default",
                stage or "default",
                agent or "",
                provider or "ollama",
                model or "qwen2.5-coder:7b",
                prompt_tokens,
                completion_tokens,
                total,
                latency_ms,
                1 if success else 0,
                error,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

        logger.debug(
            "LLM call recorded: project=%s stage=%s tokens=%d latency=%.0fms",
            project_id,
            stage,
            total,
            latency_ms,
        )

    def get_project_summary(self, project_id: str) -> ProjectCostSummary:
        """Get full cost summary for a project."""
        rows = self._conn.execute(
            """
            SELECT stage, provider, model,
                   SUM(prompt_tokens), SUM(completion_tokens),
                   SUM(total_tokens), AVG(latency_ms),
                   SUM(latency_ms), COUNT(*),
                   SUM(CASE WHEN success=1 THEN 1 ELSE 0 END)
            FROM llm_calls
            WHERE project_id = ?
            GROUP BY stage
            ORDER BY SUM(total_tokens) DESC
            """,
            (project_id,),
        ).fetchall()

        stages: list[StageCostSummary] = []
        total_tokens = 0
        total_latency = 0.0
        total_calls = 0

        for row in rows:
            (
                stage,
                provider,
                model,
                pt,
                ct,
                tt,
                avg_lat,
                sum_lat,
                calls,
                successes,
            ) = row
            st_calls = calls or 0
            st_succ = successes or 0
            stages.append(
                StageCostSummary(
                    stage=stage or "unknown",
                    llm_calls=st_calls,
                    total_tokens=tt or 0,
                    prompt_tokens=pt or 0,
                    completion_tokens=ct or 0,
                    avg_latency_ms=avg_lat or 0.0,
                    total_latency_ms=sum_lat or 0.0,
                    success_rate=(st_succ / st_calls if st_calls else 0.0),
                    retries=max(0, st_calls - 1),
                )
            )
            total_tokens += tt or 0
            total_latency += sum_lat or 0.0
            total_calls += st_calls

        most_expensive = stages[0].stage if stages else "none"
        slowest = max(stages, key=lambda s: s.avg_latency_ms, default=None)

        cost = self._estimate_cost(rows)

        return ProjectCostSummary(
            project_id=project_id,
            total_llm_calls=total_calls,
            total_tokens=total_tokens,
            total_latency_seconds=round(total_latency / 1000, 1),
            stages=stages,
            most_expensive_stage=most_expensive,
            slowest_stage=slowest.stage if slowest else "none",
            estimated_cost_usd=round(cost, 4),
        )

    def get_stage_calls(self, project_id: str, stage: str) -> list[dict[str, Any]]:
        """Get individual calls for one stage."""
        rows = self._conn.execute(
            """
            SELECT call_id, provider, model, prompt_tokens,
                   completion_tokens, total_tokens, latency_ms,
                   success, error, called_at
            FROM llm_calls
            WHERE project_id=? AND stage=?
            ORDER BY called_at ASC
            """,
            (project_id, stage),
        ).fetchall()
        return [
            {
                "call_id": r[0],
                "provider": r[1],
                "model": r[2],
                "prompt_tokens": r[3],
                "completion_tokens": r[4],
                "total_tokens": r[5],
                "latency_ms": round(r[6], 0),
                "success": bool(r[7]),
                "error": r[8],
                "called_at": r[9],
            }
            for r in rows
        ]

    def get_stage_cost(self, stage: str) -> CostSummary:
        """Return aggregated CostSummary for legacy callers."""
        return self._summarize("WHERE stage = ?", (stage,))

    def get_project_cost(self, project_id: str) -> CostSummary:
        """Return aggregated CostSummary for legacy callers."""
        return self._summarize("WHERE project_id = ?", (project_id,))

    def get_total(self) -> CostSummary:
        """Return aggregated CostSummary for legacy callers."""
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

    @staticmethod
    def _lookup_prices(model: str) -> dict[str, float]:
        """Return pricing for ``model``, with prefix-match fallback.

        Exact lookup first; if not found, find the longest key in
        TOKEN_COST_PER_1K that the model string starts with, separated by
        a ``-`` boundary.  This handles versioned suffixes like
        ``gemini-2.0-flash-001`` → ``gemini-2.0-flash``.
        Returns ``{}`` (zero cost) if nothing matches.
        """
        if model in TOKEN_COST_PER_1K:
            return TOKEN_COST_PER_1K[model]
        # Find the longest matching prefix key (boundary must be at '-' or end)
        best_key = ""
        for key in TOKEN_COST_PER_1K:
            if model.startswith(key) and len(key) > len(best_key):
                # Ensure the match stops at a segment boundary, not mid-word
                tail = model[len(key):]
                if tail == "" or tail.startswith("-"):
                    best_key = key
        return TOKEN_COST_PER_1K[best_key] if best_key else {}

    def _estimate_cost(self, rows: list[tuple]) -> float:
        total = 0.0
        for row in rows:
            model = row[2] or ""
            pt = row[3] or 0
            ct = row[4] or 0
            prices = self._lookup_prices(model)
            total += (pt / 1000) * prices.get("input", 0.0)
            total += (ct / 1000) * prices.get("output", 0.0)
        return total
