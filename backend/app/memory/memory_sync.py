from __future__ import annotations

from typing import Any


class MemorySynchronization:
    """Tracks synchronization state across memory store and cache."""

    def __init__(self) -> None:
        self._synced: bool = False

    def mark_synced(self) -> None:
        self._synced = True

    def is_synced(self) -> bool:
        return self._synced
