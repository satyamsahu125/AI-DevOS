from __future__ import annotations

from abc import ABC, abstractmethod

from .request import LLMRequest
from .response import LLMResponse


class BaseLLMProvider(ABC):
    """Documented base class for LLM providers."""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
