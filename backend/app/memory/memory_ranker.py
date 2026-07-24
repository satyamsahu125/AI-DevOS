from __future__ import annotations

from typing import Any


class MemoryRanker:
    """Ranks memory items by relevance for the current stage."""

    def rank(self, items: list[Any]) -> list[Any]:
        return sorted(items, key=lambda item: str(item), reverse=True)
