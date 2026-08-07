from __future__ import annotations

from typing import Any


class AgentMonitor:
    """Provides basic runtime monitoring hooks for agents."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def record(self, event: dict[str, Any]) -> None:
        self._events.append(event)

    def events(self) -> list[dict[str, Any]]:
        return list(self._events)
