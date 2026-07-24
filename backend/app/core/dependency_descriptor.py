from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class DependencyDescriptor:
    """Describes a dependency that can be created by the container."""

    name: str
    factory: Callable[[], Any] | None = None
    dependency_type: str = "service"
    metadata: dict[str, Any] = field(default_factory=dict)
