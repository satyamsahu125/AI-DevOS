"""auth.py — API key authentication middleware for AI DevOS.

Minimum viable auth: reads X-API-Key from request headers and validates it
against a comma-separated list in the VALID_API_KEYS environment variable.

Security properties:
- Zero-database: keys live in .env only (no DB required, no secret table)
- Constant-time comparison via hmac.compare_digest (prevents timing attacks)
- Exempts health and documentation endpoints (always accessible)
- Returns 401 on missing key, 403 on invalid key — distinct for client debugging

Configuration:
    VALID_API_KEYS=key1,key2,key3   # comma-separated list in .env
    If VALID_API_KEYS is not set or empty, auth is DISABLED (all requests pass through).
    This allows existing dev environments to work without adding a key immediately.

Usage (in main.py):
    from .api.middleware.auth import APIKeyMiddleware
    app.add_middleware(APIKeyMiddleware)
"""

from __future__ import annotations

import hmac
import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Endpoints that bypass auth — always accessible
_EXEMPT_PATHS = {
    "/health",
    "/ready",
    "/docs",
    "/openapi.json",
    "/redoc",
}

_HEADER_NAME = "X-API-Key"


def _load_valid_keys() -> frozenset[str]:
    """Load valid API keys from VALID_API_KEYS env var (comma-separated)."""
    raw = os.environ.get("VALID_API_KEYS", "").strip()
    if not raw:
        return frozenset()
    keys = {k.strip() for k in raw.split(",") if k.strip()}
    return frozenset(keys)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that validates X-API-Key on every request.

    When VALID_API_KEYS is not set or empty, auth is disabled and all requests
    pass through — safe for dev environments that haven't configured keys yet.
    """

    def __init__(self, app, **kwargs) -> None:
        """Load valid keys from env at startup — not on every request."""
        super().__init__(app, **kwargs)
        self._valid_keys = _load_valid_keys()
        if not self._valid_keys:
            logger.warning(
                "[APIKeyMiddleware] VALID_API_KEYS not configured — auth is DISABLED. "
                "Set VALID_API_KEYS=<key1>,<key2> in .env to enable authentication."
            )
        else:
            logger.info("[APIKeyMiddleware] auth enabled with %d valid key(s)", len(self._valid_keys))

    async def dispatch(self, request: Request, call_next):
        """Validate X-API-Key header if auth is enabled."""
        # Auth disabled — pass through
        if not self._valid_keys:
            return await call_next(request)

        # Exempt health/docs endpoints
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        key = request.headers.get(_HEADER_NAME)
        if not key:
            logger.warning("[APIKeyMiddleware] 401 — missing X-API-Key: path=%s", request.url.path)
            return JSONResponse(
                status_code=401,
                content={"detail": "X-API-Key header is required"},
            )

        # Constant-time comparison to prevent timing attacks
        if not any(hmac.compare_digest(key, valid_key) for valid_key in self._valid_keys):
            logger.warning("[APIKeyMiddleware] 403 — invalid X-API-Key: path=%s", request.url.path)
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid API key"},
            )

        return await call_next(request)
