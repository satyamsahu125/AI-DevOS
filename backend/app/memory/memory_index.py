from __future__ import annotations

from typing import Any


class MemoryIndex:
    """Indexes memory records by key for fast lookup."""

    def __init__(self) -> None:
        self._index: dict[str, Any] = {}

    def add(self, key: str, value: Any) -> None:
        self._index[key] = value

    def get(self, key: str) -> Any | None:
        return self._index.get(key)

    def remove(self, key: str) -> None:
        self._index.pop(key, None)

    def snapshot(self) -> dict[str, Any]:
        return dict(self._index)
