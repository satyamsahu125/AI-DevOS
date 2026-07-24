from __future__ import annotations

from ..shared.exceptions import LLMException
from .request import LLMRequest


class LLMRuntimeValidator:
    """Validates LLM requests before execution."""

    def validate(self, request: LLMRequest) -> None:
        if not request.user_prompt:
            raise LLMException("user prompt is required")
