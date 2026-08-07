from __future__ import annotations

from typing import Any


class MemoryFilter:
    """Filters memory items by relevance and validity."""

    def filter(self, items: list[Any]) -> list[Any]:
        return [item for item in items if item not in (None, "", [], {}, ())]
