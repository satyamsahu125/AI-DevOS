from __future__ import annotations

from typing import Any


class ContextFilters:
    """Filters out empty context values before building the final context."""

    def filter(self, values: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in values.items() if value not in (None, "", [], {}, ())}
