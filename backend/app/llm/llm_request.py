from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class LLMRequest:
    """Normalized request model for LLM execution."""

    request_id: str
    provider: str
    model: str
    messages: list[dict[str, str]] = field(default_factory=list)
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 256
    stop_sequences: list[str] = field(default_factory=list)
    stream: bool = False
    timeout: int = 30
    metadata: dict[str, Any] = field(default_factory=dict)
