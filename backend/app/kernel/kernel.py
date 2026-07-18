from __future__ import annotations

from .bootstrap import Bootstrap
from .lifecycle import LifecycleManager


class AIKernel:
    def __init__(self, bootstrap: Bootstrap | None = None, lifecycle: LifecycleManager | None = None) -> None:
        self._bootstrap = bootstrap or Bootstrap()
        self._lifecycle = lifecycle or LifecycleManager(self._bootstrap)

    def start(self) -> None:
        self._lifecycle.startup()

    def stop(self) -> None:
        self._lifecycle.shutdown()
