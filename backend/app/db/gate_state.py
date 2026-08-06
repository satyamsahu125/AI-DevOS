"""R10 — RedisGateStateRegistry: distributed gate state storage.

Replaces the per-process in-memory dict used by the gate pause mechanism
with Redis-backed storage — enabling multiple API instances to share the
same gate state without a sticky-session load balancer.

Design:
    - Falls back to thread-safe in-memory dict when Redis is unreachable or
      REDIS_URL is not set, so the single-instance deployment path is unchanged.
    - Keys: devos:gate:{project_id} — Redis hash, one field per gate name.
    - TTL: 24 hours per hash (reset on each write) — prevents orphaned keys.
    - Serialization: JSON per field — forward-compatible with richer gate data.
    - Thread-safe: in-memory path uses threading.Lock; Redis path is
      inherently safe (atomic HSET/HGET).

Usage (via DI container):
    registry = container.resolve("gate_state_registry")
    registry.set(project_id, "architecture", {"status": "pending", ...})
    state = registry.get(project_id, "architecture")   # dict | None
    registry.clear(project_id)                          # on project delete
    all_gates = registry.get_all(project_id)           # dict[gate_name, data]

Architecture compliance:
    - Stateless: registry holds no per-request state.
    - Single responsibility: owns only gate state read/write.
    - No direct agent-to-agent communication — gates speak through this registry.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "").strip()
_KEY_PREFIX = "devos:gate:"
_TTL_SECONDS = 86_400  # 24 hours


# ---------------------------------------------------------------------------
# Public factory — returns best available backend
# ---------------------------------------------------------------------------

def build_gate_state_registry() -> "GateStateRegistry":
    """Return a RedisGateStateRegistry if Redis is reachable, else InMemoryGateStateRegistry.

    Probes Redis connection once at startup. Non-fatal — any error falls back
    to in-memory. Called once by the DI container.
    """
    if _REDIS_URL:
        try:
            import redis as _redis_module
            client = _redis_module.Redis.from_url(_REDIS_URL, socket_connect_timeout=2, decode_responses=True)
            client.ping()
            logger.info("[GateStateRegistry] Redis backend active: url=%s", _REDIS_URL)
            return RedisGateStateRegistry(client)
        except ImportError:
            logger.warning("[GateStateRegistry] redis package not installed — using in-memory fallback")
        except Exception as exc:
            logger.warning(
                "[GateStateRegistry] Redis unreachable (%s) — using in-memory fallback", exc
            )
    else:
        logger.info("[GateStateRegistry] REDIS_URL not set — using in-memory gate state (single-instance)")
    return InMemoryGateStateRegistry()


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class GateStateRegistry:
    """Abstract gate state store. Concrete implementations below."""

    def get(self, project_id: str, gate_name: str) -> dict[str, Any] | None:
        """Return gate data for (project_id, gate_name), or None if absent."""
        raise NotImplementedError

    def get_all(self, project_id: str) -> dict[str, dict[str, Any]]:
        """Return all gate data for project_id as {gate_name: data}."""
        raise NotImplementedError

    def set(self, project_id: str, gate_name: str, data: dict[str, Any]) -> None:
        """Persist gate data for (project_id, gate_name)."""
        raise NotImplementedError

    def delete(self, project_id: str, gate_name: str) -> None:
        """Remove a single gate entry."""
        raise NotImplementedError

    def clear(self, project_id: str) -> None:
        """Remove all gate state for project_id (call on project delete)."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Redis-backed implementation
# ---------------------------------------------------------------------------

class RedisGateStateRegistry(GateStateRegistry):
    """Stores gate state in Redis hashes keyed by project_id.

    Key schema: devos:gate:{project_id}
    Field schema: {gate_name} → JSON(data)
    TTL: 24 hours, reset on each write.
    """

    def __init__(self, client: Any) -> None:
        self._redis = client

    def _key(self, project_id: str) -> str:
        return f"{_KEY_PREFIX}{project_id}"

    def get(self, project_id: str, gate_name: str) -> dict[str, Any] | None:
        try:
            raw = self._redis.hget(self._key(project_id), gate_name)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("[RedisGateStateRegistry] get failed: %s", exc)
            return None

    def get_all(self, project_id: str) -> dict[str, dict[str, Any]]:
        try:
            raw_map = self._redis.hgetall(self._key(project_id))
            result: dict[str, dict[str, Any]] = {}
            for gate_name, raw in (raw_map or {}).items():
                try:
                    result[gate_name] = json.loads(raw)
                except Exception:
                    pass
            return result
        except Exception as exc:
            logger.warning("[RedisGateStateRegistry] get_all failed: %s", exc)
            return {}

    def set(self, project_id: str, gate_name: str, data: dict[str, Any]) -> None:
        try:
            key = self._key(project_id)
            self._redis.hset(key, gate_name, json.dumps(data, default=str))
            self._redis.expire(key, _TTL_SECONDS)
        except Exception as exc:
            logger.warning("[RedisGateStateRegistry] set failed: %s", exc)

    def delete(self, project_id: str, gate_name: str) -> None:
        try:
            self._redis.hdel(self._key(project_id), gate_name)
        except Exception as exc:
            logger.warning("[RedisGateStateRegistry] delete failed: %s", exc)

    def clear(self, project_id: str) -> None:
        try:
            self._redis.delete(self._key(project_id))
        except Exception as exc:
            logger.warning("[RedisGateStateRegistry] clear failed: %s", exc)


# ---------------------------------------------------------------------------
# In-memory fallback (single-instance, thread-safe)
# ---------------------------------------------------------------------------

class InMemoryGateStateRegistry(GateStateRegistry):
    """Thread-safe in-memory gate state store.

    Identical interface to RedisGateStateRegistry. Used when Redis is not
    configured or unreachable. Data is lost on process restart — acceptable
    for single-instance deployments where the gate mechanism already relies
    on project.json as the durable state.
    """

    def __init__(self) -> None:
        # {project_id: {gate_name: data}}
        self._store: dict[str, dict[str, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def get(self, project_id: str, gate_name: str) -> dict[str, Any] | None:
        with self._lock:
            return self._store.get(project_id, {}).get(gate_name)

    def get_all(self, project_id: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._store.get(project_id, {}))

    def set(self, project_id: str, gate_name: str, data: dict[str, Any]) -> None:
        with self._lock:
            if project_id not in self._store:
                self._store[project_id] = {}
            self._store[project_id][gate_name] = data

    def delete(self, project_id: str, gate_name: str) -> None:
        with self._lock:
            if project_id in self._store:
                self._store[project_id].pop(gate_name, None)

    def clear(self, project_id: str) -> None:
        with self._lock:
            self._store.pop(project_id, None)


# ---------------------------------------------------------------------------
# Module-level singleton (used by gates.py before DI is wired)
# ---------------------------------------------------------------------------

_registry_instance: GateStateRegistry | None = None
_registry_lock = threading.Lock()


def get_gate_state_registry() -> GateStateRegistry:
    """Return the process-wide gate state registry (lazy singleton).

    Called by gates.py for backward compat. Container.build() will call
    build_gate_state_registry() and register it as "gate_state_registry",
    but this function covers the case where gates.py is hit before the
    container is fully built (e.g. health checks, test fixtures).
    """
    global _registry_instance
    if _registry_instance is None:
        with _registry_lock:
            if _registry_instance is None:
                _registry_instance = build_gate_state_registry()
    return _registry_instance
