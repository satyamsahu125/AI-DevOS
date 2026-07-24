from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class ServiceDescriptor:
    """Describes a runtime service registration."""

    name: str
    kind: str
    factory: Callable[[], Any] | None = None
    lifetime: str = "singleton"
    metadata: dict[str, Any] = field(default_factory=dict)
