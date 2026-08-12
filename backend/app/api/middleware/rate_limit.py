"""R8 — In-memory sliding-window rate limiter.

Pre-R10 implementation: stores counters in a process-level dict.
Post-R10 (Redis): replace the _store dict with Redis ZRANGEBYSCORE.

Limits enforced:
  - DEFAULT_LIMIT req/min per user (default 60)
  - PIPELINE_LIMIT pipeline starts/hour per user (default 5)
  - CHAT_LIMIT chat messages/hour per user (default 100)
  - PROJECT_CREATE_LIMIT project creates/min per API key (default 10, spec-mandated)

When RATE_LIMIT_ENABLED=false (default), all requests pass through.

Phase 6 addition: RateLimitMiddleware class wires project-create rate limiting
into the FastAPI middleware stack (registered via app.add_middleware).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "false").lower() in ("true", "1", "yes")
DEFAULT_LIMIT = int(os.getenv("RATE_LIMIT_DEFAULT", "60"))               # req/min
PIPELINE_LIMIT = int(os.getenv("RATE_LIMIT_PIPELINE", "5"))              # pipeline starts/hr
CHAT_LIMIT = int(os.getenv("RATE_LIMIT_CHAT", "100"))                    # chat messages/hr
# Phase 6 spec: 10 project creates per minute per API key
PROJECT_CREATE_LIMIT = int(os.getenv("RATE_LIMIT_PROJECT_CREATE", "10"))  # creates/min

# Paths that count as project creation (POST only).
# Comma-separated env override: RATE_LIMIT_PROJECT_PATHS=/api/v1/projects,/projects
_raw_paths = os.getenv("RATE_LIMIT_PROJECT_PATHS", "/api/v1/projects,/projects")
_PROJECT_CREATE_PATHS: frozenset[str] = frozenset(
    p.strip() for p in _raw_paths.split(",") if p.strip()
)

# _store: key → deque of timestamps (float seconds)
_store: dict[str, deque] = {}
_lock = threading.Lock()


def _check_limit(key: str, limit: int, window_seconds: int) -> None:
    """Sliding-window check. Raises HTTPException(429) if over limit.

    Parameters
    ----------
    key : str
        Unique identifier for this rate-limit bucket (e.g. "user:abc123:default").
    limit : int
        Maximum number of requests allowed in window_seconds.
    window_seconds : int
        Length of the sliding window in seconds.
    """
    if not RATE_LIMIT_ENABLED:
        return

    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        if key not in _store:
            _store[key] = deque()
        dq = _store[key]
        # Evict entries outside the window
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            # Retry-After: seconds until the oldest entry expires
            retry_after = int(dq[0] + window_seconds - now) + 1
            logger.warning("[rate_limit] 429: key=%s limit=%d window=%ds", key, limit, window_seconds)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
        dq.append(now)


def check_default(user_id: str) -> None:
    """60 requests/minute per user."""
    _check_limit(f"user:{user_id}:default", DEFAULT_LIMIT, 60)


def check_pipeline(user_id: str) -> None:
    """5 pipeline starts/hour per user."""
    _check_limit(f"user:{user_id}:pipeline", PIPELINE_LIMIT, 3600)


def check_chat(user_id: str) -> None:
    """100 chat messages/hour per user."""
    _check_limit(f"user:{user_id}:chat", CHAT_LIMIT, 3600)


def check_project_create(api_key: str) -> None:
    """10 project creates/minute per API key (spec Phase 6)."""
    _check_limit(f"project_create:{api_key}", PROJECT_CREATE_LIMIT, 60)


# ---------------------------------------------------------------------------
# Phase 6: FastAPI middleware class for project-create rate limiting
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter for project creation endpoints.

    Intercepts POST requests to project-creation paths and enforces
    PROJECT_CREATE_LIMIT per API key per minute when RATE_LIMIT_ENABLED=true.

    Disabled by default (RATE_LIMIT_ENABLED=false) so existing dev workflows
    are unaffected. Enable in production by setting RATE_LIMIT_ENABLED=true.

    Phase 6 spec: "Rate limiting middleware (10 project creates per minute per key)."
    """

    async def dispatch(self, request: Request, call_next):
        if RATE_LIMIT_ENABLED and request.method == "POST":
            path = request.url.path
            # Check whether this request targets a project-creation endpoint.
            if any(path == target or path.rstrip("/") == target.rstrip("/")
                   for target in _PROJECT_CREATE_PATHS):
                api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key", "")
                # Fall back to client IP when no API key header is present
                bucket = api_key or (request.client.host if request.client else "unknown")
                try:
                    check_project_create(bucket)
                except HTTPException as exc:
                    return JSONResponse(
                        status_code=exc.status_code,
                        content={"detail": exc.detail},
                        headers=dict(exc.headers or {}),
                    )
        return await call_next(request)
