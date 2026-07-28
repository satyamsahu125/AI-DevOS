from __future__ import annotations

import logging

from .providers.base_provider import LLMProvider
from .providers.bedrock_provider import BedrockProvider
from .providers.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


class LLMFactory:
    """Creates the provider instance for a configured provider name."""

    def create_provider(
        self,
        provider_name: str,
        base_url: str | None = None,
        bedrock_api_key: str = "",
        bedrock_region: str = "us-east-1",
        timeout: int = 1200,
    ) -> LLMProvider:
        """Return a provider instance matching provider_name ("ollama"/"default"/"bedrock")."""
        logger.debug("creating llm provider: name=%s base_url=%s timeout=%s", provider_name, base_url, timeout)
        name = provider_name.lower()
        if name in {"ollama", "default"}:
            return OllamaProvider(base_url=base_url, timeout=timeout) if base_url else OllamaProvider(timeout=timeout)
        if name == "bedrock":
            return BedrockProvider(api_key=bedrock_api_key, region=bedrock_region)
        raise ValueError(f"Unsupported provider: {provider_name}")
