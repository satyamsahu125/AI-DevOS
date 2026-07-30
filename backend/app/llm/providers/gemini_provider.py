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

_BASE_URL = "https://generativelanguage.googleapis.com"

# Known Gemini models
_KNOWN_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-1.5-pro",
]


class GeminiProvider(LLMProvider):
    """LLM provider that calls the Google Generative Language (Gemini) API.

    Authentication: pass the API key from Google AI Studio (makersuite.google.com)
    as api_key.  The key is appended as a query parameter on every request.

    json_mode: when request.json_mode is True, the generation config sets
    responseMimeType to 'application/json', which forces the model to emit
    valid JSON without markdown fences.  This is the native Gemini equivalent
    of Ollama's format="json" grammar-constrained decoding.

    Default model: gemini-2.0-flash — fast, high context window (1M tokens),
    strong at structured JSON output, well-suited for architecture stages.
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = _BASE_URL,
        timeout: int = 1200,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._initialized = False

    # ── LLMProvider interface ────────────────────────────────────────────────

    def initialize(self) -> None:
        self._initialized = True

    def execute(self, request: LLMRequest) -> LLMResponse:
        ProviderValidation.validate_request(request)
        model = request.model or "gemini-2.0-flash"
        payload = self._build_payload(request)
        path = f"/v1beta/models/{model}:generateContent?key={self.api_key}"
        started = time.time()
        try:
            body = self._post_json(path, payload)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.warning("gemini execute failed: model=%s error=%s", model, exc)
            raise ProviderValidationException(f"gemini execution failed: {exc}") from exc
        elapsed = time.time() - started
        logger.debug("gemini execute ok: model=%s latency=%.3fs", model, elapsed)
        return self._map_response(request, body, elapsed)

    def stream(self, request: LLMRequest) -> Iterator[LLMResponse]:
        """Yield a single response (streaming not yet implemented; falls back to execute)."""
        yield self.execute(request)

    def health(self) -> ProviderHealth:
        """Check reachability by calling the models list endpoint."""
        try:
            path = f"/v1beta/models?key={self.api_key}"
            self._get_json(path)
            return ProviderHealth(
                status="ok", provider=self.provider_name(),
                reachable=True, models_loaded=len(_KNOWN_MODELS),
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.debug("gemini health check failed: %s", exc)
            return ProviderHealth(
                status="unhealthy", provider=self.provider_name(), reachable=False
            )

    def shutdown(self) -> None:
        self._initialized = False

    def validate(self, request: LLMRequest) -> None:
        ProviderValidation.validate_request(request)

    def provider_name(self) -> str:
        return "gemini"

    def supported_models(self) -> list[str]:
        return list(_KNOWN_MODELS)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=False,
            embeddings=False,
            json_mode=True,
            structured_output=True,
            supported_models=self.supported_models(),
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _build_payload(self, request: LLMRequest) -> dict:
        """Build the Gemini generateContent payload.

        Gemini uses a 'contents' list with role=user/model alternating turns.
        System instructions go in a separate top-level 'systemInstruction' field.
        json_mode: responseMimeType="application/json" instructs the model to
        output only valid JSON — no markdown fences, no prose.
        """
        system_parts = [
            m["content"] for m in request.messages if m.get("role") == "system"
        ]
        contents = []
        for m in request.messages:
            if m.get("role") == "system":
                continue
            # Gemini roles: "user" or "model" (not "assistant")
            role = "user" if m.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        generation_config: dict = {
            "maxOutputTokens": request.max_tokens,
            "temperature": request.temperature,
            "topP": request.top_p,
        }
        if getattr(request, "json_mode", False):
            # Native JSON mode: forces valid JSON output without fences
            generation_config["responseMimeType"] = "application/json"

        payload: dict = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_parts:
            payload["systemInstruction"] = {
                "parts": [{"text": "\n\n".join(system_parts)}]
            }

        return payload

    def _map_response(self, request: LLMRequest, body: dict, latency: float) -> LLMResponse:
        candidates = body.get("candidates", [])
        text = ""
        finish_reason = "stop"
        if candidates:
            cand = candidates[0]
            finish_reason = cand.get("finishReason", "STOP").lower()
            content = cand.get("content", {})
            parts = content.get("parts", [])
            text = "".join(p.get("text", "") for p in parts)

        usage_meta = body.get("usageMetadata", {})
        prompt_tokens = int(usage_meta.get("promptTokenCount", 0))
        completion_tokens = int(usage_meta.get("candidatesTokenCount", 0))

        return LLMResponse(
            response_id=f"gemini-{request.request_id}",
            provider=self.provider_name(),
            model=request.model,
            content=text,
            usage={
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens,
            },
            finish_reason=finish_reason,
            latency=latency,
            metadata={"raw": body},
        )

    def _post_json(self, path: str, payload: dict) -> dict:
        req = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _get_json(self, path: str) -> dict:
        req = Request(f"{self.base_url}{path}", method="GET")
        with urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
