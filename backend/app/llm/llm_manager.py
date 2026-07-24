from __future__ import annotations

import time
from typing import Any

from ..shared.exceptions import DependencyException
from .llm_metrics import LLMMetrics
from .llm_request import LLMRequest
from .llm_response import LLMResponse
from .llm_validation import LLMValidation


class LLMManager:
    """Coordinates provider selection, request validation, retries, and metrics."""

    def __init__(self, provider: Any | None = None, config: Any | None = None) -> None:
        self.provider = provider
        self.config = config
        self._metrics = LLMMetrics()
        self._provider_name = "default"

    def initialize(self) -> None:
        self._metrics.requests = 0

    def execute(self, request: LLMRequest) -> LLMResponse:
        LLMValidation.validate_request(request)
        self._metrics.requests += 1
        self._metrics.last_provider = request.provider
        self._metrics.last_model = request.model
        attempts = 0
        last_error: Exception | None = None
        while attempts < 3:
            try:
                started = time.time()
                response = self._call_provider(request)
                self._metrics.total_latency_ms += (time.time() - started) * 1000
                return response
            except Exception as exc:  # noqa: BLE001
                attempts += 1
                self._metrics.retries += 1
                self._metrics.errors += 1
                last_error = exc
        raise DependencyException(f"llm execution failed: {last_error}") if last_error else DependencyException("llm execution failed")

    def stream(self, request: LLMRequest) -> LLMResponse:
        return self.execute(request)

    def validate(self, request: LLMRequest) -> None:
        LLMValidation.validate_request(request)

    def shutdown(self) -> None:
        self._metrics.requests = 0

    def health(self) -> bool:
        return True

    def metrics(self) -> LLMMetrics:
        return self._metrics

    def provider(self) -> str:
        return self._provider_name

    def _call_provider(self, request: LLMRequest) -> LLMResponse:
        if self.provider is None:
            response = LLMResponse(
                response_id=f"resp-{self._metrics.requests}",
                provider=request.provider,
                model=request.model,
                content="",
                usage={"prompt": 0, "completion": 0, "total": 0},
            )
            LLMValidation.validate_response(response)
            return response
        response = self.provider.generate(request)
        LLMValidation.validate_response(response)
        return response
