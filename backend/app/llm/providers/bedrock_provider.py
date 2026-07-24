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


class BedrockProvider(LLMProvider):
    """Concrete LLMProvider that calls AWS Bedrock Runtime's Converse API using a Bedrock API key
    (Bearer-token auth) rather than SigV4 -- see https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html.
    request.model is expected to be a Bedrock model id (e.g. "qwen.qwen3-coder-480b-a35b-v1:0").
    """

    def __init__(self, api_key: str = "", region: str = "us-east-1", timeout: int = 600) -> None:
        self.api_key = api_key
        self.region = region
        self.timeout = timeout
        self._initialized = False

    def initialize(self) -> None:
        self._initialized = True

    def execute(self, request: LLMRequest) -> LLMResponse:
        ProviderValidation.validate_request(request)
        if not self.api_key:
            raise ProviderValidationException("bedrock api key is not configured")
        payload = self._build_payload(request)
        started = time.time()
        try:
            body = self._post_json(f"/model/{request.model}/converse", payload)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.warning("bedrock execution failed: model=%s error=%s", request.model, exc)
            raise ProviderValidationException(f"bedrock execution failed: {exc}") from exc
        elapsed = time.time() - started
        logger.debug("bedrock execute ok: model=%s latency=%.3fs", request.model, elapsed)
        return self._map_response(request, body, elapsed)

    def stream(self, request: LLMRequest) -> Iterator[LLMResponse]:
        """No incremental streaming support; yields the single completed response."""
        yield self.execute(request)

    def health(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(status="unhealthy", provider=self.provider_name(), reachable=False)
        return ProviderHealth(status="ok", provider=self.provider_name(), reachable=True, models_loaded=0)

    def shutdown(self) -> None:
        self._initialized = False

    def validate(self, request: LLMRequest) -> None:
        ProviderValidation.validate_request(request)

    def provider_name(self) -> str:
        return "bedrock"

    def supported_models(self) -> list[str]:
        """Bedrock has no unauthenticated model-listing call comparable to Ollama's /api/tags;
        the caller picks a model id from the account's model catalog directly."""
        return []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=False, embeddings=False, json_mode=True, structured_output=True, supported_models=[])

    def _build_payload(self, request: LLMRequest) -> dict[str, object]:
        system_messages = [m["content"] for m in request.messages if m.get("role") == "system"]
        conversation = [
            {"role": m["role"], "content": [{"text": m["content"]}]}
            for m in request.messages
            if m.get("role") != "system"
        ]
        payload: dict[str, object] = {
            "messages": conversation,
            "inferenceConfig": {
                "temperature": request.temperature,
                "topP": request.top_p,
                "maxTokens": request.max_tokens,
            },
        }
        if system_messages:
            payload["system"] = [{"text": text} for text in system_messages]
        return payload

    def _post_json(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        url = f"https://bedrock-runtime.{self.region}.amazonaws.com{path}"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urlopen(request, timeout=self.timeout) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def _map_response(self, request: LLMRequest, body: dict[str, object], latency: float = 0.0) -> LLMResponse:
        message = ((body.get("output") or {}).get("message") or {}) if isinstance(body, dict) else {}
        content_blocks = message.get("content", []) if isinstance(message, dict) else []
        text = "".join(block.get("text", "") for block in content_blocks if isinstance(block, dict))
        usage = body.get("usage", {}) if isinstance(body, dict) else {}
        input_tokens = int(usage.get("inputTokens", 0)) if isinstance(usage, dict) else 0
        output_tokens = int(usage.get("outputTokens", 0)) if isinstance(usage, dict) else 0
        return LLMResponse(
            response_id=f"bedrock-{request.request_id}",
            provider=self.provider_name(),
            model=request.model,
            content=text,
            usage={"prompt": input_tokens, "completion": output_tokens, "total": input_tokens + output_tokens},
            finish_reason=str(body.get("stopReason", "stop")) if isinstance(body, dict) else "stop",
            latency=latency,
            metadata={"raw": body},
        )
