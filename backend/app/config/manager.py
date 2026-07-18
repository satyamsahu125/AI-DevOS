from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..shared.exceptions import ConfigurationException
from .loader import ConfigurationLoader
from .models import Settings
from .validator import ConfigurationValidator


class ConfigurationManager:
    def __init__(self, loader: ConfigurationLoader | None = None, validator: ConfigurationValidator | None = None) -> None:
        self._loader = loader or ConfigurationLoader()
        self._validator = validator or ConfigurationValidator()
        self._settings: Optional[Settings] = None

    def load(self, path: Path | None = None) -> Settings:
        settings = self._loader.load(path)
        self._validator.validate(settings)
        self._settings = settings
        return settings

    def settings(self) -> Settings:
        if self._settings is None:
            raise ConfigurationException("configuration has not been loaded")
        return self._settings
