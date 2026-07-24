from __future__ import annotations

from ..shared.exceptions import LLMException
from .provider_registry import ProviderRegistry
from .request import LLMRequest
from .response import LLMResponse
from .runtime_validation import LLMRuntimeValidator


class LLMRuntime:
    """Coordinates LLM provider selection and execution."""

    def __init__(self, provider_registry: ProviderRegistry | None = None, validator: LLMRuntimeValidator | None = None) -> None:
        self.provider_registry = provider_registry or ProviderRegistry()
        self.validator = validator or LLMRuntimeValidator()

    def execute(self, request: LLMRequest) -> LLMResponse:
        self.validator.validate(request)
        provider = self.provider_registry.resolve(request.model)
        if provider is None:
            raise LLMException("no provider available")
        return provider.generate(request)
