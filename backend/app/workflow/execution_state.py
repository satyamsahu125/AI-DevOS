from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "").strip()
_EXEC_STATE_KEY_PREFIX = "exec_state:"
_EXEC_STATE_TTL = 86_400  # 24 hours


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class ExecutionStateRegistry:
    """Abstract execution state store. Concrete implementations below."""

    def mark_running(self, project_id: str) -> None:
        raise NotImplementedError

    def mark_stopped(self, project_id: str) -> None:
        raise NotImplementedError

    def is_running(self, project_id: str) -> bool:
        raise NotImplementedError

    def request_stop(self, project_id: str) -> bool:
        raise NotImplementedError

    def is_stop_requested(self, project_id: str) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# In-memory implementation (original)
# ---------------------------------------------------------------------------

class InMemoryExecutionState(ExecutionStateRegistry):
    """In-memory execution state registry. Per-process, not shared across workers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running: dict[str, int] = {}
        self._stop_requested: set[str] = set()

    def mark_running(self, project_id: str) -> None:
        with self._lock:
            self._running[project_id] = self._running.get(project_id, 0) + 1
            if self._running[project_id] == 1:
                self._stop_requested.discard(project_id)

    def mark_stopped(self, project_id: str) -> None:
        with self._lock:
            if project_id in self._running:
                self._running[project_id] -= 1
                if self._running[project_id] <= 0:
                    del self._running[project_id]

    def is_running(self, project_id: str) -> bool:
        with self._lock:
            return project_id in self._running

    def request_stop(self, project_id: str) -> bool:
        with self._lock:
            if project_id not in self._running:
                return False
            self._stop_requested.add(project_id)
            return True

    def is_stop_requested(self, project_id: str) -> bool:
        with self._lock:
            return project_id in self._stop_requested


# ---------------------------------------------------------------------------
# Redis-backed implementation (shared across workers)
# ---------------------------------------------------------------------------

class RedisExecutionState(ExecutionStateRegistry):
    """Redis-backed execution state registry. Shared across Celery workers."""

    def __init__(self, redis_client, ttl_seconds: int = 86_400) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, project_id: str) -> str:
        return f"{_EXEC_STATE_KEY_PREFIX}{project_id}"

    def _load(self, project_id: str) -> dict[str, Any] | None:
        raw = self._redis.get(self._key(project_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def _save(self, project_id: str, data: dict[str, Any]) -> None:
        self._redis.setex(self._key(project_id), self._ttl, json.dumps(data))

    def mark_running(self, project_id: str) -> None:
        data = self._load(project_id) or {"running": 0, "stop_requested": False}
        data["running"] = data.get("running", 0) + 1
        if data["running"] == 1:
            data["stop_requested"] = False
        self._save(project_id, data)

    def mark_stopped(self, project_id: str) -> None:
        data = self._load(project_id)
        if data is None:
            return
        data["running"] = max(0, data.get("running", 1) - 1)
        if data["running"] == 0:
            data.pop("running", None)
            # If nothing else in data, delete the key
            if not data:
                self._redis.delete(self._key(project_id))
                return
        self._save(project_id, data)

    def is_running(self, project_id: str) -> bool:
        data = self._load(project_id)
        return bool(data and data.get("running", 0) > 0)

    def request_stop(self, project_id: str) -> bool:
        data = self._load(project_id)
        if not data or data.get("running", 0) == 0:
            return False
        data["stop_requested"] = True
        self._save(project_id, data)
        return True

    def is_stop_requested(self, project_id: str) -> bool:
        data = self._load(project_id)
        return bool(data and data.get("stop_requested", False))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_execution_state_registry() -> ExecutionStateRegistry:
    """Return RedisExecutionState if REDIS_URL is set and reachable, else InMemoryExecutionState."""
    if _REDIS_URL:
        try:
            import redis as _redis_module
            client = _redis_module.Redis.from_url(_REDIS_URL, socket_connect_timeout=2, decode_responses=True)
            client.ping()
            logger.info("[ExecutionStateRegistry] Redis backend active: url=%s", _REDIS_URL)
            return RedisExecutionState(client)
        except ImportError:
            logger.warning("[ExecutionStateRegistry] redis package not installed — using in-memory fallback")
        except Exception as exc:
            logger.warning(
                "[ExecutionStateRegistry] Redis unreachable (%s) — using in-memory fallback", exc
            )
    else:
        logger.info("[ExecutionStateRegistry] REDIS_URL not set — using in-memory execution state (single-instance)")
    return InMemoryExecutionState()


# Backward compatibility alias
ExecutionStateRegistry = InMemoryExecutionState
