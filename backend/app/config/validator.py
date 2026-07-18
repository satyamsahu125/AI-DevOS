from __future__ import annotations

from ..shared.exceptions import ConfigurationException
from .models import Settings


class ConfigurationValidator:
    def validate(self, settings: Settings) -> None:
        if not settings.llm.provider:
            raise ConfigurationException("llm provider is required")
        if not settings.llm.model:
            raise ConfigurationException("llm model is required")
        if settings.runtime.retry_limit <= 0:
            raise ConfigurationException("retry limit must be positive")
