from __future__ import annotations

import logging

from .providers.base_provider import LLMProvider
from .providers.bedrock_provider import BedrockProvider
from .providers.claude_provider import ClaudeProvider
from .providers.gemini_provider import GeminiProvider
from .providers.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


class LLMFactory:
    """Creates the provider instance for a configured provider name.

    Supported provider names:
      "ollama" / "default"  — local Ollama server
      "claude"              — Anthropic Claude Messages API
      "gemini"              — Google Gemini Generative Language API
      "bedrock"             — AWS Bedrock
    """

    def create_provider(
        self,
        provider_name: str,
        base_url: str | None = None,
        api_key: str = "",
        bedrock_api_key: str = "",
        bedrock_region: str = "us-east-1",
        timeout: int = 1200,
    ) -> LLMProvider:
        """Return a fully initialized provider instance matching provider_name."""
        logger.debug(
            "creating llm provider: name=%s base_url=%s timeout=%s",
            provider_name, base_url, timeout,
        )
        name = provider_name.lower()

        if name in {"ollama", "default"}:
            if base_url:
                return OllamaProvider(base_url=base_url, timeout=timeout)
            return OllamaProvider(timeout=timeout)

        if name == "claude":
            key = api_key or bedrock_api_key  # reuse bedrock_api_key slot for compat
            # Never inherit base_url from config when provider is Claude — the
            # config base_url is the Ollama server address (http://localhost:11434)
            # and passing it here routes Claude calls to Ollama, returning 404.
            # Claude always uses the Anthropic API endpoint; allow override only
            # if it explicitly looks like an Anthropic URL (custom proxy support).
            claude_url = (
                base_url
                if base_url and "localhost" not in base_url and "127.0.0.1" not in base_url
                else "https://api.anthropic.com"
            )
            return ClaudeProvider(api_key=key, base_url=claude_url, timeout=timeout)

        if name == "gemini":
            key = api_key or bedrock_api_key
            # Same reasoning: never use the Ollama localhost URL for Gemini.
            gemini_url = (
                base_url
                if base_url and "localhost" not in base_url and "127.0.0.1" not in base_url
                else "https://generativelanguage.googleapis.com"
            )
            return GeminiProvider(api_key=key, base_url=gemini_url, timeout=timeout)

        if name == "bedrock":
            return BedrockProvider(api_key=bedrock_api_key or api_key, region=bedrock_region, timeout=timeout)

        raise ValueError(
            f"Unsupported provider: '{provider_name}'. "
            f"Valid options: ollama, claude, gemini, bedrock"
        )
