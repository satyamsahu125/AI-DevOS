from __future__ import annotations

from typing import Any


class ContextCollector:
    """Collects runtime context values for assembly."""

    def collect(self, **values: Any) -> dict[str, Any]:
        return dict(values)
