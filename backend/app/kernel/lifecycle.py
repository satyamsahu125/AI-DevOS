from __future__ import annotations

from .bootstrap import Bootstrap


class LifecycleManager:
    def __init__(self, bootstrap: Bootstrap | None = None) -> None:
        self._bootstrap = bootstrap or Bootstrap()
        self._started = False

    def startup(self) -> None:
        self._bootstrap.initialize()
        self._started = True

    def shutdown(self) -> None:
        self._started = False
