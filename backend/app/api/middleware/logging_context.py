"""logging_context.py — Per-request structured logging context middleware.

Phase 6 spec: "Structured logging middleware (adds project_id to every log line)"

Binds two context fields to every log record emitted during a request:
  - request_id: UUID (from X-Request-ID header or auto-generated)
  - project_id: extracted from common URL path patterns (e.g. /workflow/{id}/...)

Works with the existing _JSONFormatter and _TextFormatter in
observability/logging.py — those formatters already read `project_id` and
`request_id` from log record attributes when present.

Implementation:
  1. contextvars.ContextVar — stores request_id and project_id for the duration
     of each request coroutine (correct for async FastAPI).
  2. _RequestContextFilter — a logging.Filter registered on the root logger that
     reads the contextvars and injects them into every log record.
  3. LoggingContextMiddleware — FastAPI/Starlette BaseHTTPMiddleware that sets
     the contextvars at request entry and resets them at response exit.

The filter is registered once (guarded by _filter_installed) when the
middleware class is first instantiated. It does not accumulate on repeated
add_middleware calls because logging.Logger.addFilter is idempotent when the
same instance is not re-added.
"""

from __future__ import annotations

import contextvars
import logging
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-request context variables
# ---------------------------------------------------------------------------

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)
_project_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "project_id", default=""
)

# Regex patterns for extracting project_id from URL paths.
# Matches: /workflow/{id}/... or /projects/{id} or /api/v1/projects/{id}/...
_PROJECT_ID_PATTERNS = [
    re.compile(r"/workflow/([a-zA-Z0-9_-]{4,})"),
    re.compile(r"/projects/([a-zA-Z0-9_-]{4,})"),
    re.compile(r"/api/v\d+/projects/([a-zA-Z0-9_-]{4,})"),
]


def _extract_project_id(path: str) -> str:
    """Return project_id from a URL path, or empty string when not found."""
    for pattern in _PROJECT_ID_PATTERNS:
        m = pattern.search(path)
        if m:
            return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# Logging filter — reads contextvars and injects into every log record
# ---------------------------------------------------------------------------

class _RequestContextFilter(logging.Filter):
    """Inject request_id and project_id into every log record.

    Reads from contextvars so it is safe for concurrent async requests —
    each request coroutine has its own context.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Do not overwrite fields already set explicitly via extra=
        if not getattr(record, "request_id", None):
            record.request_id = _request_id_var.get("")  # type: ignore[attr-defined]
        if not getattr(record, "project_id", None):
            record.project_id = _project_id_var.get("")  # type: ignore[attr-defined]
        return True


# Singleton filter — installed once on the root logger.
_context_filter = _RequestContextFilter()
_filter_installed = False


def _install_filter() -> None:
    """Register the context filter on the root logger (idempotent)."""
    global _filter_installed
    if _filter_installed:
        return
    logging.getLogger().addFilter(_context_filter)
    _filter_installed = True
    logger.debug("[logging_context] _RequestContextFilter installed on root logger")


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class LoggingContextMiddleware(BaseHTTPMiddleware):
    """Bind request_id and project_id to the log context for every request.

    Phase 6 spec: "Structured logging middleware (adds project_id to every log line)"

    At request entry:
      - Reads X-Request-ID header or generates a short UUID.
      - Extracts project_id from URL path if present.
      - Binds both to contextvars for the lifetime of the request.

    At response exit (including errors):
      - Resets the contextvars so they don't leak into unrelated coroutines.
    """

    def __init__(self, app, **kwargs) -> None:
        super().__init__(app, **kwargs)
        _install_filter()

    async def dispatch(self, request: Request, call_next):
        # Prefer caller-supplied request ID; fall back to short UUID.
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        project_id = _extract_project_id(request.url.path)

        token_rid = _request_id_var.set(request_id)
        token_pid = _project_id_var.set(project_id)
        try:
            response = await call_next(request)
            return response
        finally:
            _request_id_var.reset(token_rid)
            _project_id_var.reset(token_pid)
