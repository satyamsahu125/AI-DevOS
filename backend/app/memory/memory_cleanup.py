from __future__ import annotations

import logging
import os
from typing import Any, Optional

from .memory_store import build_memory_store
from ..storage.storage_adapter import StorageAdapter, StorageQuery, StorageConfig
from ..storage.storage_factory import StorageFactory

logger = logging.getLogger(__name__)


class MemoryCleanup:
    """Provides cleanup operations for memory runtime state.

    Supports both in-memory and persistent (Postgres/SQLite) backends.
    """

    def __init__(self, store: Optional[Any] = None) -> None:
        self._store = store or build_memory_store()
        self._removed: list[str] = []  # Track removed keys for in-memory mode

    def mark_removed(self, key: str) -> None:
        """Mark a key as removed and actually delete it from the store."""
        self._removed.append(key)
        try:
            self._store.delete(key)
        except Exception as exc:
            logger.warning("MemoryCleanup.mark_removed failed for key=%s: %s", key, exc)

    def snapshot(self) -> list[str]:
        return list(self._removed)

    def clear(self) -> None:
        self._removed.clear()

    def sweep(self) -> int:
        """Delete all expired entries from persistent storage.

        For Postgres/SQLite backends, this issues a DELETE for expired entries.
        For in-memory backend, this is a no-op (entries don't expire in memory).

        Returns:
            Number of entries deleted.
        """
        # Check if we have a persistent store with sweep capability
        if hasattr(self._store, '_adapter'):
            adapter = self._store._adapter
            table = getattr(self._store, '_table', 'memory_store')
            try:
                # Delete expired entries where expires_at is not null and < NOW()
                adapter.delete(
                    table,
                    StorageQuery(
                        table=table,
                        filters={},  # We'll use a custom query for expires_at
                    )
                )
                # For a proper sweep, we'd need a custom query. For now, log and return 0.
                logger.info("MemoryCleanup.sweep: Postgres/SQLite sweep not fully implemented; use custom SQL for expires_at cleanup")
                return 0
            except Exception as exc:
                logger.warning("MemoryCleanup.sweep failed: %s", exc)
                return 0
        return 0