from __future__ import annotations

from ..kernel.bootstrap import Bootstrap


class RuntimeStartup:
    """Small startup wrapper for the runtime bootstrap."""

    def __init__(self, bootstrap: Bootstrap | None = None) -> None:
        """Wire the Bootstrap this startup wrapper delegates to."""
        self._bootstrap = bootstrap or Bootstrap()

    def start(self) -> object:
        """Run bootstrap and return the resulting Runtime."""
        return self._bootstrap.initialize()
