from __future__ import annotations

from typing import Any


class AgentRegistry:
    """Maintains agent registrations and metadata for the runtime."""

    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}
        self.descriptors: dict[str, Any] = {}

    def register(self, name: str, descriptor: Any) -> None:
        self.agents[name] = descriptor
        self.descriptors[name] = descriptor

    def resolve(self, name: str) -> Any:
        return self.agents[name]

    def has(self, name: str) -> bool:
        return name in self.agents

    def list_agents(self) -> list[str]:
        return sorted(self.agents)
