from __future__ import annotations

from ..config.manager import ConfigurationManager
from .factory import LLMFactory
from .request import LLMRequest
from .response import LLMResponse


class LLMManager:
    """Small manager that uses the configured provider for text generation."""

    def __init__(self, config_manager: ConfigurationManager | None = None, factory: LLMFactory | None = None) -> None:
        self._config_manager = config_manager or ConfigurationManager()
        self._factory = factory or LLMFactory()
        self._settings = self._config_manager.load()
        self._provider = self._factory.create_provider(self._settings.llm.provider)

    def generate_requirements(self, request: str) -> str:
        return f"Requirements for: {request}"

    def generate_text(self, prompt: str, system_prompt: str = "", model: str | None = None) -> LLMResponse:
        settings = self._settings
        request = LLMRequest(
            system_prompt=system_prompt,
            user_prompt=prompt,
            model=model or settings.llm.model,
            temperature=settings.llm.temperature,
            max_tokens=settings.llm.max_tokens,
        )
        return self._provider.generate(request)
