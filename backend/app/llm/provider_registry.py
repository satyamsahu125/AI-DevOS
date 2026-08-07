from __future__ import annotations

from typing import Any

from .providers.ollama_provider import OllamaProvider


class ProviderRegistry:
    """Tracks available LLM providers."""

    def __init__(self) -> None:
        self._providers: dict[str, Any] = {}
        self.register("default", OllamaProvider())

    def register(self, name: str, provider: Any) -> None:
        self._providers[name] = provider

    def resolve(self, name: str) -> Any:
        if name in self._providers:
            return self._providers[name]
        return self._providers.get("default")
