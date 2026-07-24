from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator

from ..llm_request import LLMRequest
from ..llm_response import LLMResponse
from .provider_health import ProviderHealth
from .provider_capabilities import ProviderCapabilities


class LLMProvider(ABC):
    """Contract for interchangeable LLM providers."""

    @abstractmethod
    def initialize(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def execute(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    def stream(self, request: LLMRequest) -> Iterator[LLMResponse]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def validate(self, request: LLMRequest) -> None:
        raise NotImplementedError

    @abstractmethod
    def provider_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def supported_models(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def capabilities(self) -> ProviderCapabilities:
        raise NotImplementedError
