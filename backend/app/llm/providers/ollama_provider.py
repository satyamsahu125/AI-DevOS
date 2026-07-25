from __future__ import annotations

import json
import logging
import time
from typing import Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..llm_request import LLMRequest
from ..llm_response import LLMResponse
from .base_provider import LLMProvider
from .provider_capabilities import ProviderCapabilities
from .provider_health import ProviderHealth
from .provider_validation import ProviderValidation, ProviderValidationException

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Concrete LLMProvider that calls a local Ollama server's /api/generate and /api/tags endpoints."""

    def __init__(self, base_url: str = "http://localhost:11434", timeout: int = 600) -> None:
        """Wire the Ollama server's base URL and request timeout.

        600s default: a full role-specific prompt against a 7B local model
        commonly takes 40-120s+ on modest hardware depending on how large
        the requested JSON schema is (Designer's, with several nested
        lists, measured ~118s) -- the previous 30s default caused real
        stage calls to time out (see run.sh/test_run.sh verification).
        Code-generation stages (BackendDeveloper/FrontendDeveloper) push
        this further: they combine a larger injected context (approved
        architecture + design spec) with a response that embeds full file
        contents, not just a JSON schema shell -- FrontendDeveloper measured
        two consecutive real timeouts at 240s before this was raised.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._initialized = False

    def initialize(self) -> None:
        """Mark this provider as initialized (no connection is opened eagerly)."""
        self._initialized = True

    def execute(self, request: LLMRequest) -> LLMResponse:
        """Send request to Ollama's /api/generate and return the mapped LLMResponse, timing the call."""
        ProviderValidation.validate_request(request)
        payload = self._build_payload(request)
        started = time.time()
        try:
            body = self._post_json("/api/generate", payload)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.warning("ollama execution failed: model=%s error=%s", request.model, exc)
            raise ProviderValidationException(f"ollama execution failed: {exc}") from exc
        elapsed = time.time() - started
        logger.debug("ollama execute ok: model=%s latency=%.3fs", request.model, elapsed)
        return self._map_response(request, body, elapsed)

    def stream(self, request: LLMRequest) -> Iterator[LLMResponse]:
        """Stream a single mapped LLMResponse from Ollama (no incremental chunking)."""
        ProviderValidation.validate_request(request)
        payload = self._build_payload(request, stream=True)
        started = time.time()
        try:
            body = self._post_json("/api/generate", payload)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.warning("ollama stream failed: model=%s error=%s", request.model, exc)
            raise ProviderValidationException(f"ollama stream failed: {exc}") from exc
        yield self._map_response(request, body, time.time() - started)

    def health(self) -> ProviderHealth:
        """Report whether the Ollama server is reachable, and how many models it has loaded."""
        try:
            body = self._get_json("/api/tags")
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.debug("ollama health check failed: %s", exc)
            return ProviderHealth(status="unhealthy", provider=self.provider_name(), reachable=False)
        models = body.get("models", []) if isinstance(body, dict) else []
        return ProviderHealth(status="ok", provider=self.provider_name(), reachable=True, models_loaded=len(models))

    def shutdown(self) -> None:
        """Mark this provider as no longer initialized."""
        self._initialized = False

    def validate(self, request: LLMRequest) -> None:
        """Validate request has the fields ProviderValidation requires."""
        ProviderValidation.validate_request(request)

    def provider_name(self) -> str:
        """Return this provider's canonical name."""
        return "ollama"

    def supported_models(self) -> list[str]:
        """Return the model names currently loaded on the Ollama server, or [] if unreachable."""
        try:
            body = self._get_json("/api/tags")
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.debug("ollama supported_models failed: %s", exc)
            return []
        models = body.get("models", []) if isinstance(body, dict) else []
        return [item.get("name", "") for item in models if isinstance(item, dict)]

    def capabilities(self) -> ProviderCapabilities:
        """Describe this provider's supported features."""
        return ProviderCapabilities(streaming=True, embeddings=True, json_mode=True, structured_output=True, supported_models=self.supported_models())

    def _build_payload(self, request: LLMRequest, stream: bool = False) -> dict[str, object]:
        """Build the Ollama /api/generate payload, splitting system-role messages into the top-level `system` field."""
        system_messages = [m["content"] for m in request.messages if m.get("role") == "system"]
        user_messages = [m["content"] for m in request.messages if m.get("role") != "system"]
        payload: dict[str, object] = {
            "model": request.model,
            "prompt": user_messages[-1] if user_messages else "",
            "stream": stream,
            "options": {
                "temperature": request.temperature,
                "top_p": request.top_p,
                "num_predict": request.max_tokens,
            },
        }
        if system_messages:
            payload["system"] = system_messages[-1]
        return payload

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def _get_json(self, path: str) -> dict[str, object]:
        request = Request(f"{self.base_url}{path}", method="GET")
        with urlopen(request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def _map_response(self, request: LLMRequest, body: dict[str, object], latency: float = 0.0) -> LLMResponse:
        """Map an Ollama /api/generate response body (plus measured latency, in seconds) to an LLMResponse."""
        content = body.get("response", "") if isinstance(body, dict) else ""
        return LLMResponse(
            response_id=f"ollama-{request.request_id}",
            provider=self.provider_name(),
            model=request.model,
            content=str(content),
            usage={
                "prompt": int(body.get("prompt_eval_count", 0)),
                "completion": int(body.get("eval_count", 0)),
                "total": int(body.get("prompt_eval_count", 0)) + int(body.get("eval_count", 0)),
            },
            finish_reason="stop" if body.get("done") else "length",
            latency=latency,
            metadata={"raw": body},
        )
