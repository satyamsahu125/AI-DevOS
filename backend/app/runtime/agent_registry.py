from __future__ import annotations

from .agent_factory import AgentFactory


class AgentRegistry:
    """Registers the supported agent types for the runtime."""

    def __init__(self, factory: AgentFactory | None = None) -> None:
        self.factory = factory or AgentFactory()
        self._registry = {
            "product_owner": "product_owner",
            "reviewer": "reviewer",
            "architect": "architect",
            "planner": "planner",
            "backend": "backend",
            "frontend": "frontend",
            "qa": "qa",
            "devops": "devops",
        }

    def get(self, name: str) -> str | None:
        return self._registry.get(name)
