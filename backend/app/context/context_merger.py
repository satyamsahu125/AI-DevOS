from __future__ import annotations

from typing import Any


class ContextMerger:
    """Merges context dictionaries into a single payload."""

    def merge(self, *parts: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for part in parts:
            merged.update(part)
        return merged
