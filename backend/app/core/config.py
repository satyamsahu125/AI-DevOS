from __future__ import annotations

from pathlib import Path

from ..config.manager import ConfigurationManager
from ..config.models import Settings


class CoreConfig:
    """Convenience wrapper for accessing runtime configuration from core."""

    def __init__(self, manager: ConfigurationManager | None = None) -> None:
        self._manager = manager or ConfigurationManager()

    def load(self, path: Path | None = None) -> Settings:
        return self._manager.load(path)

    def settings(self) -> Settings:
        return self._manager.settings()
