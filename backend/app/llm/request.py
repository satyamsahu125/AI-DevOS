from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LLMRequest:
    system_prompt: str
    user_prompt: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 256
    stream: bool = False
