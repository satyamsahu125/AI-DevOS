from __future__ import annotations

from typing import Any

from ..shared.exceptions import DependencyException


class DependencyResolver:
    """Small resolver that delegates container lookups."""

    def __init__(self, container: Any | None = None) -> None:
        self.container = container

    def resolve(self, name: str) -> Any:
        if self.container is None:
            raise DependencyException("container is not configured")
        return self.container.resolve(name)
