"""request_size.py — Request body size limit middleware.

Phase 6 spec: "Request size limit (reject bodies > 50KB)"

Rejects requests whose Content-Length header exceeds MAX_BODY_BYTES.
Returns HTTP 413 Request Entity Too Large.

Content-Length is checked before the body is read, so oversized payloads
are rejected without consuming server memory.

Chunked-encoded requests (no Content-Length header) pass through — they are
rare and handling them requires buffering the entire body, which defeats the
purpose of the check. Production deployments should place a reverse proxy
(nginx/Caddy) in front that enforces a body size limit unconditionally.

Configuration:
    REQUEST_MAX_BODY_BYTES — override limit (default: 51200 = 50KB)
"""

from __future__ import annotations

import logging
import os

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

_DEFAULT_MAX = 50 * 1024  # 50 KB

MAX_BODY_BYTES: int = int(os.getenv("REQUEST_MAX_BODY_BYTES", str(_DEFAULT_MAX)))


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with Content-Length > MAX_BODY_BYTES.

    Phase 6 spec: prevents 500,000-character descriptions from being embedded
    in every LLM prompt and consuming Bedrock credits without validation.

    Already-validated endpoints (e.g. api/project.py) perform character-level
    checks; this middleware is a defence-in-depth layer at the HTTP boundary.
    """

    def __init__(self, app, max_body_bytes: int = MAX_BODY_BYTES, **kwargs) -> None:
        super().__init__(app, **kwargs)
        self._max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                body_size = int(content_length)
            except ValueError:
                body_size = 0
            if body_size > self._max_body_bytes:
                logger.warning(
                    "[request_size] 413: content-length=%d limit=%d path=%s",
                    body_size, self._max_body_bytes, request.url.path,
                )
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            f"Request body too large. "
                            f"Maximum allowed size is {self._max_body_bytes // 1024} KB."
                        )
                    },
                )
        return await call_next(request)
