from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ProviderCapabilities:
    """Describes the capabilities a provider exposes."""

    streaming: bool = False
    embeddings: bool = False
    vision: bool = False
    function_calling: bool = False
    json_mode: bool = False
    structured_output: bool = False
    max_tokens: int = 4096
    supported_models: list[str] = field(default_factory=list)
