from __future__ import annotations

from .request import LLMRequest


class RequestPipeline:
    """Prepares an LLM request for runtime execution."""

    def build(self, prompt: str, system_prompt: str = "", model: str | None = None) -> LLMRequest:
        return LLMRequest(system_prompt=system_prompt, user_prompt=prompt, model=model or "default", temperature=0.0, max_tokens=256)
