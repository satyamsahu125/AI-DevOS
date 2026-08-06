from __future__ import annotations

import json
import logging
import os
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
    """Calls AWS Bedrock Runtime's Converse API.

    Supports two authentication modes (chosen automatically):

    1. **Bearer token** — set BEDROCK_API_KEY in .env.
       Uses ``Authorization: Bearer <key>`` (AWS Bedrock API-key feature).
       Simplest option; no AWS SDK required.

    2. **SigV4 via boto3** — set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY
       (or configure ~/.aws/credentials / IAM role).
       Used when BEDROCK_API_KEY is empty or absent.
       Requires ``boto3`` to be installed (included in requirements.txt).

    request.model must be a Bedrock model ID, e.g.:
      anthropic.claude-3-5-sonnet-20241022-v2:0
      us.deepseek.r1-v1:0
      amazon.nova-pro-v1:0
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
        if not self.api_key and not self._has_boto3_credentials():
            raise ProviderValidationException(
                "bedrock: no credentials configured. "
                "Set BEDROCK_API_KEY for Bearer-token auth, or set "
                "AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY for SigV4 auth."
            )
        payload = self._build_payload(request)
        started = time.time()
        try:
            if self.api_key:
                body = self._post_bearer(f"/model/{request.model}/converse", payload)
            else:
                body = self._post_sigv4(f"/model/{request.model}/converse", payload, request.model)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            logger.warning("bedrock execution failed: model=%s error=%s", request.model, exc)
            raise ProviderValidationException(f"bedrock execution failed: {exc}") from exc
        elapsed = time.time() - started
        logger.debug("bedrock execute ok: model=%s latency=%.3fs auth=%s",
                     request.model, elapsed, "bearer" if self.api_key else "sigv4")
        return self._map_response(request, body, elapsed)

    def stream(self, request: LLMRequest) -> Iterator[LLMResponse]:
        """No incremental streaming; yields the single completed response."""
        yield self.execute(request)

    def health(self) -> ProviderHealth:
        has_creds = bool(self.api_key) or self._has_boto3_credentials()
        if not has_creds:
            return ProviderHealth(status="unhealthy", provider=self.provider_name(), reachable=False)
        return ProviderHealth(status="ok", provider=self.provider_name(), reachable=True, models_loaded=0)

    def shutdown(self) -> None:
        self._initialized = False

    def validate(self, request: LLMRequest) -> None:
        ProviderValidation.validate_request(request)

    def provider_name(self) -> str:
        return "bedrock"

    def supported_models(self) -> list[str]:
        return []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            streaming=False, embeddings=False,
            json_mode=True, structured_output=True, supported_models=[],
        )

    # ── Payload builder ───────────────────────────────────────────────────────

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

    # ── Auth mode 1: Bearer token ─────────────────────────────────────────────

    def _post_bearer(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        url = f"https://bedrock-runtime.{self.region}.amazonaws.com{path}"
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    # ── Auth mode 2: SigV4 via boto3 ─────────────────────────────────────────

    @staticmethod
    def _has_boto3_credentials() -> bool:
        """Return True if boto3 is installed AND AWS credentials are discoverable."""
        try:
            import boto3  # noqa: F401
            import botocore  # noqa: F401
        except ImportError:
            return False
        # Fast check: at least one of the standard env-var credential sources is set
        if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
            return True
        # Could also have ~/.aws/credentials or IAM role — let boto3 decide at call time
        try:
            import boto3
            session = boto3.Session()
            creds = session.get_credentials()
            return creds is not None and creds.get_frozen_credentials() is not None
        except Exception:
            return False

    def _post_sigv4(self, path: str, payload: dict[str, object], model_id: str) -> dict[str, object]:
        """Sign the request with SigV4 using botocore and send it via urllib."""
        try:
            import boto3
            from botocore.auth import SigV4Auth
            from botocore.awsrequest import AWSRequest
        except ImportError as exc:
            raise ProviderValidationException(
                "boto3 is required for SigV4 auth. "
                "Install it: pip install boto3"
            ) from exc

        url = f"https://bedrock-runtime.{self.region}.amazonaws.com{path}"
        body_bytes = json.dumps(payload).encode("utf-8")

        # Build a botocore AWSRequest for signing
        aws_request = AWSRequest(
            method="POST",
            url=url,
            data=body_bytes,
            headers={"Content-Type": "application/json"},
        )

        session = boto3.Session(region_name=self.region)
        credentials = session.get_credentials()
        if credentials is None:
            raise ProviderValidationException(
                "No AWS credentials found. Configure AWS_ACCESS_KEY_ID + "
                "AWS_SECRET_ACCESS_KEY, or set up ~/.aws/credentials."
            )

        SigV4Auth(credentials, "bedrock", self.region).add_auth(aws_request)

        # Transfer signed headers to a urllib Request
        req = Request(url, data=body_bytes, method="POST")
        for header, value in aws_request.headers.items():
            req.add_header(header, value)

        with urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    # ── Response mapper ───────────────────────────────────────────────────────

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
