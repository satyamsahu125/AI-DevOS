from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Settings


class ConfigurationLoader:
    def __init__(self) -> None:
        self._config_paths = [
            Path(__file__).resolve().parents[2] / "config" / "config.yaml",
            Path(__file__).resolve().parents[1] / "config" / "config.yaml",
        ]

    def load(self, path: Path | None = None) -> Settings:
        config_path = path
        if config_path is None:
            config_path = next((candidate for candidate in self._config_paths if candidate.exists()), self._config_paths[0])
        if not config_path.exists():
            return Settings()
        payload: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        return Settings(**payload)
