from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelProfile:
    """Per-stage LLM routing profile.

    Carries provider + model overrides and optional generation parameter
    overrides. When a field is None, LLMManager falls back to the globally
    configured value from Settings.
    """

    provider: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None

    def __repr__(self) -> str:
        return (
            f"ModelProfile(provider={self.provider!r}, model={self.model!r}, "
            f"temperature={self.temperature}, max_tokens={self.max_tokens})"
        )
