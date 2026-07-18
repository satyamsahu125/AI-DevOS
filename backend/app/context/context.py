from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentContext:
    project_name: str = ""
    requirements: str = ""
    architecture: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextManager:
    """Builds a context payload for an agent execution step."""

    def build(self, request: str, **kwargs: Any) -> dict[str, Any]:
        return {"request": request, **kwargs}


class ContextBuilder(ContextManager):
    """Backward-compatible alias for the context manager."""

    pass
