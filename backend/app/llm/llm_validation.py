from __future__ import annotations

from ..shared.exceptions import DependencyException


class LLMValidation:
    """Validates LLM requests and responses."""

    @staticmethod
    def validate_request(request: object) -> None:
        if request is None:
            raise DependencyException("llm request is required")
        if not getattr(request, "provider", None):
            raise DependencyException("llm provider is required")
        if not getattr(request, "model", None):
            raise DependencyException("llm model is required")
        if getattr(request, "timeout", 0) <= 0:
            raise DependencyException("llm timeout must be positive")

    @staticmethod
    def validate_response(response: object) -> None:
        if response is None:
            raise DependencyException("llm response is required")
        if not getattr(response, "content", None):
            raise DependencyException("response content is required")
