from __future__ import annotations

import logging
from typing import Any

from .sqlite_storage_adapter import SQLiteStorageAdapter
from .storage_adapter import MemoryStorageAdapter, StorageAdapter, StorageConfig

logger = logging.getLogger(__name__)


class StorageFactory:
    """Factory for StorageAdapter instances, selecting an implementation by config.driver."""

    @staticmethod
    def create(config: StorageConfig, logger: Any | None = None) -> StorageAdapter:
        """Build and initialize the StorageAdapter matching config.driver ("memory" or "sqlite")."""
        if config.driver == "memory":
            adapter = MemoryStorageAdapter(config=config, logger=logger)
            adapter.initialize()
            return adapter
        if config.driver == "sqlite":
            adapter = SQLiteStorageAdapter(config=config, logger=logger)
            adapter.initialize()
            return adapter
        raise ValueError(f"unsupported storage driver: {config.driver}")
