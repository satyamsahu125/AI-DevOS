from __future__ import annotations

from ..session.checkpoint import CheckpointManager
from .bootstrap import Bootstrap
from .lifecycle import LifecycleManager


class AIKernel:
    def __init__(self, bootstrap: Bootstrap | None = None, lifecycle: LifecycleManager | None = None) -> None:
        self._bootstrap = bootstrap or Bootstrap()
        self._lifecycle = lifecycle or LifecycleManager(self._bootstrap)
        self.container = self._bootstrap._container

    def start(self) -> None:
        self._lifecycle.startup()
        checkpoint_manager = CheckpointManager()
        checkpoint_manager.cleanup_old_checkpoints(days=7)

    def stop(self) -> None:
        self._lifecycle.shutdown()
