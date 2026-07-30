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

# Anthropic API version header — required on every request
_ANTHROPIC_VERSION = "2023-06-01"
_BASE_URL = "https://api.anthropic.com"

# Known Claude models available via the Anthropic Messages API.
# IMPORTANT: the API requires date-stamped model IDs.  Shorthand aliases like
# "claude-sonnet-4-5" (without a date) return HTTP 404 — always use the full
# versioned string shown below.
_KNOWN_MODELS = [
    # Claude 3.5 (stable, production-ready)
    "claude-3-5-sonnet-20241022",   # recommended default — strong JSON
    "claude-3-5-haiku-20241022",    # fast and cheap
    # Claude 3
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
    # Claude 4 / 4.5 — use these only if your account has access
    "claude-haiku-4-5-20251001",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-opus-4-0",
    "claude-sonnet-4-0",
]


class ClaudeProvider(LLMProvider):
    """LLM provider that calls the Anthropic Claude Messages API.

    Authentication: pass the API key via LLMConfig.bedrock_api_key (field
    is reused for non-Bedrock API keys) or set ANTHROPIC_API_KEY env var.
    Recommended model: claude-haiku-4-5 (fast, cheap, strong at JSON).
    For architecture-heavy stages use claude-sonnet-4-5.

    json_mode: when request.json_mode is True we add a prefill assistant
    message starting with '{' which strongly nudges Claude to emit a bare
    JSON object.  The Anthropic API itself has no dedicated json_mode flag.
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
        payload = self._build_payload(request)
        started = time.time()
        try:
            body = self._post_json("/v1/messages", payload)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.warning("claude execute failed: model=%s error=%s", request.model, exc)
            raise ProviderValidationException(f"claude execution failed: {exc}") from exc
        elapsed = time.time() - started
        logger.debug("claude execute ok: model=%s latency=%.3fs", request.model, elapsed)
        return self._map_response(request, body, elapsed)

    def stream(self, request: LLMRequest) -> Iterator[LLMResponse]:
        """Yield a single response (streaming not yet implemented; falls back to execute)."""
        yield self.execute(request)

    def health(self) -> ProviderHealth:
        """Check reachability by calling the models list endpoint."""
        try:
            self._get_json("/v1/models")
            return ProviderHealth(
                status="ok", provider=self.provider_name(),
                reachable=True, models_loaded=len(_KNOWN_MODELS),
            )
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.debug("claude health check failed: %s", exc)
            return ProviderHealth(
                status="unhealthy", provider=self.provider_name(), reachable=False
            )

    def shutdown(self) -> None:
        self._initialized = False

    def validate(self, request: LLMRequest) -> None:
        ProviderValidation.validate_request(request)

    def provider_name(self) -> str:
        return "claude"

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
        """Build the Anthropic Messages API payload.

        System messages are extracted into the top-level 'system' field.
        When json_mode is True, an assistant prefill of '{' steers the
        model toward outputting a bare JSON object without markdown fences.
        """
        system_parts = [
            m["content"] for m in request.messages if m.get("role") == "system"
        ]
        user_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in request.messages
            if m.get("role") != "system"
        ]

        payload: dict = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": user_messages,
            "temperature": request.temperature,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        logger.info(
            "claude payload: model=%s max_tokens=%s temperature=%s "
            "system_len=%s user_messages=%s json_mode=%s",
            payload["model"], payload["max_tokens"], payload["temperature"],
            len(payload.get("system", "")),
            [(m["role"], len(m.get("content", ""))) for m in user_messages],
            getattr(request, "json_mode", False),
        )

        # JSON prefill: forces the model to continue from an open brace,
        # producing a bare JSON object without any markdown wrapper.
        if getattr(request, "json_mode", False):
            payload["messages"] = list(user_messages) + [
                {"role": "assistant", "content": "{"}
            ]

        return payload

    def _map_response(self, request: LLMRequest, body: dict, latency: float) -> LLMResponse:
        content_blocks = body.get("content", [])
        text = "".join(
            block.get("text", "") for block in content_blocks
            if block.get("type") == "text"
        )
        # When json_mode prefill was used, the '{' is already counted in
        # the response but the API returns the continuation only — prepend.
        if getattr(request, "json_mode", False) and not text.startswith("{"):
            text = "{" + text

        usage = body.get("usage", {})
        prompt_tokens = int(usage.get("input_tokens", 0))
        completion_tokens = int(usage.get("output_tokens", 0))

        return LLMResponse(
            response_id=body.get("id", f"claude-{request.request_id}"),
            provider=self.provider_name(),
            model=body.get("model", request.model),
            content=text,
            usage={
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": prompt_tokens + completion_tokens,
            },
            finish_reason=body.get("stop_reason", "stop"),
            latency=latency,
            metadata={"raw": body},
        )

    def _post_json(self, path: str, payload: dict) -> dict:
        req = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            # Read and log the error body so the Anthropic error message is
            # visible in the server log — without this the 400/401/etc reason
            # is silently swallowed and debugging is blind.
            try:
                error_body = exc.read().decode("utf-8")
                logger.error(
                    "claude API error: status=%s url=%s body=%s payload_keys=%s",
                    exc.code, exc.url, error_body,
                    list(payload.keys()),
                )
            except Exception:
                pass
            raise

    def _get_json(self, path: str) -> dict:
        req = Request(
            f"{self.base_url}{path}",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
            },
            method="GET",
        )
        with urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
