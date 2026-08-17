from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..storage.storage_factory import StorageFactory
from ..storage.storage_adapter import StorageConfig, StorageAdapter, StorageQuery

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class MemoryStore:
    """Abstract interface for a memory store. Concrete implementations below."""

    def put(self, key: str, value: Any) -> None:
        raise NotImplementedError

    def get(self, key: str) -> Any | None:
        raise NotImplementedError

    def delete(self, key: str) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# In-memory implementation (original)
# ---------------------------------------------------------------------------


class InMemoryMemoryStore(MemoryStore):
    """In-memory memory store. Per-process, not shared across workers."""

    def __init__(self) -> None:
        self.records: dict[str, Any] = field(default_factory=dict)

    def put(self, key: str, value: Any) -> None:
        self.records[key] = value

    def get(self, key: str) -> Any | None:
        return self.records.get(key)

    def delete(self, key: str) -> None:
        self.records.pop(key, None)


# ---------------------------------------------------------------------------
# Postgres-backed implementation (shared across workers)
# ---------------------------------------------------------------------------


class PostgresMemoryStore(MemoryStore):
    """Postgres-backed memory store. Shared across Celery workers via StorageAdapter."""

    def __init__(self, adapter: StorageAdapter) -> None:
        self._adapter = adapter
        self._table = "memory_store"

    def put(self, key: str, value: Any) -> None:
        self._adapter.insert(self._table, {"id": key, "memory_id": key, "value": value})

    def get(self, key: str) -> Any | None:
        result = self._adapter.select(StorageQuery(table=self._table, filters={"id": key}, limit=1))
        if result.rows:
            return result.rows[0].get("value")
        return None

    def delete(self, key: str) -> None:
        self._adapter.delete(self._table, StorageQuery(table=self._table, filters={"id": key}))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_memory_store() -> MemoryStore:
    """Return PostgresMemoryStore if MEMORY_BACKEND=postgres, else InMemoryMemoryStore."""
    backend = os.getenv("MEMORY_BACKEND", "memory").lower()
    if backend == "postgres":
        database_url = os.getenv("DATABASE_URL", "")
        if not database_url:
            logger.warning("[MemoryStore] DATABASE_URL not set — falling back to in-memory store")
            return InMemoryMemoryStore()
        try:
            config = StorageConfig(driver="postgres", database_url=database_url)
            adapter = StorageFactory.create(config)
            logger.info("[MemoryStore] Postgres backend active: url=%s", database_url)
            return PostgresMemoryStore(adapter)
        except Exception as exc:
            logger.warning("[MemoryStore] Postgres unavailable (%s) — using in-memory fallback", exc)
            return InMemoryMemoryStore()
    elif backend == "sqlite":
        database_url = os.getenv("DATABASE_URL", "")
        if not database_url:
            logger.warning("[MemoryStore] DATABASE_URL not set for sqlite — falling back to in-memory store")
            return InMemoryMemoryStore()
        try:
            config = StorageConfig(driver="sqlite", database_url=database_url)
            adapter = StorageFactory.create(config)
            logger.info("[MemoryStore] SQLite backend active: url=%s", database_url)
            return _SQLiteMemoryStore(adapter)
        except Exception as exc:
            logger.warning("[MemoryStore] SQLite unavailable (%s) — using in-memory fallback", exc)
            return InMemoryMemoryStore()
    else:
        logger.info("[MemoryStore] MEMORY_BACKEND not set or unknown — using in-memory store")
        return InMemoryMemoryStore()


# Simple wrapper for SQLite adapter to match MemoryStore interface
class _SQLiteMemoryStore(MemoryStore):
    def __init__(self, adapter) -> None:
        self._adapter = adapter
        self._table = "memory_store"

    def put(self, key: str, value: Any) -> None:
        self._adapter.insert(self._table, {"id": key, "memory_id": key, "value": value})

    def get(self, key: str) -> Any | None:
        result = self._adapter.select(StorageQuery(table=self._table, filters={"id": key}, limit=1))
        if result.rows:
            return result.rows[0].get("value")
        return None

    def delete(self, key: str) -> None:
        self._adapter.delete(self._table, StorageQuery(table=self._table, filters={"id": key}))


# Backward compatibility alias
MemoryStore = InMemoryMemoryStore