from __future__ import annotations

from typing import Any


class MemoryCleanup:
    """Provides lightweight cleanup operations for memory runtime state."""

    def __init__(self) -> None:
        self._removed: list[str] = []

    def mark_removed(self, key: str) -> None:
        self._removed.append(key)

    def snapshot(self) -> list[str]:
        return list(self._removed)

    def clear(self) -> None:
        self._removed.clear()
