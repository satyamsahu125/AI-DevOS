from __future__ import annotations

from .providers.ollama import OllamaProvider


class LLMFactory:
    """Create a provider instance for the documented LLM package."""

    def create_provider(self, provider_name: str) -> OllamaProvider:
        if provider_name.lower() in {"ollama", "default"}:
            return OllamaProvider()
        raise ValueError(f"Unsupported provider: {provider_name}")
