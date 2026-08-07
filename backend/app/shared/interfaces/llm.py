from abc import ABC, abstractmethod

from ..dto.llm_request import LLMRequest
from ..dto.llm_response import LLMResponse


class LLMInterface(ABC):
    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        raise NotImplementedError
