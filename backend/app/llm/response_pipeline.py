from __future__ import annotations

from .response import LLMResponse


class ResponsePipeline:
    """Normalizes LLM provider output into a runtime response."""

    def build(self, content: str, model: str = "default") -> LLMResponse:
        return LLMResponse(content=content, model=model, finish_reason="stop", input_tokens=0, output_tokens=0, total_tokens=0)
