from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str
    finish_reason: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
