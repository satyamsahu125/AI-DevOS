"""test_phase6_middleware.py — Phase 6 Task 2: middleware additions to main.py.

Verifies:
  1. RateLimitMiddleware: allows requests below limit; returns 429 after limit exceeded.
  2. RateLimitMiddleware: only applies to project creation paths (POST).
  3. RateLimitMiddleware: falls through when RATE_LIMIT_ENABLED is false.
  4. check_project_create(): raises 429 after PROJECT_CREATE_LIMIT calls.
  5. RequestSizeLimitMiddleware: allows requests under 50KB.
  6. RequestSizeLimitMiddleware: returns 413 for Content-Length > 50KB.
  7. RequestSizeLimitMiddleware: passes through when Content-Length header is absent.
  8. LoggingContextMiddleware: binds request_id and project_id to contextvars.
  9. LoggingContextMiddleware: resets contextvars after response (no leak).
 10. _extract_project_id(): parses known URL patterns correctly.
 11. _install_filter(): registers filter on root logger exactly once.

Running:
    cd backend
    python -m pytest tests/test_phase6_middleware.py -v
"""
from __future__ import annotations

import asyncio
import logging
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(path: str = "/api/v1/projects", method: str = "POST",
                  headers: dict | None = None):
    """Build a minimal mock Starlette Request."""
    request = MagicMock()
    request.method = method
    request.url.path = path
    request.client.host = "127.0.0.1"
    raw_headers = {k.lower(): v for k, v in (headers or {}).items()}
    request.headers.get = lambda key, default=None: raw_headers.get(key.lower(), default)
    return request


async def _noop_next(request):
    from fastapi.responses import JSONResponse
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# 1-3: RateLimitMiddleware
# ---------------------------------------------------------------------------

class TestRateLimitMiddleware:

    def setup_method(self):
        # Reset the in-process rate limit store before each test.
        import app.api.middleware.rate_limit as rl
        with rl._lock:
            rl._store.clear()

    def test_allows_requests_below_limit(self):
        """Requests under the limit must pass through with 200."""
        from app.api.middleware.rate_limit import RateLimitMiddleware, _store, _lock

        middleware = RateLimitMiddleware(app=MagicMock())
        request = _make_request(headers={"X-API-Key": "test-key-below"})

        with patch("app.api.middleware.rate_limit.RATE_LIMIT_ENABLED", True):
            with patch("app.api.middleware.rate_limit.PROJECT_CREATE_LIMIT", 5):
                response = asyncio.get_event_loop().run_until_complete(
                    middleware.dispatch(request, _noop_next)
                )
        assert response.status_code == 200

    def test_returns_429_after_limit_exceeded(self):
        """After PROJECT_CREATE_LIMIT calls, the middleware must return 429."""
        from app.api.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=MagicMock())
        request = _make_request(headers={"X-API-Key": "test-key-exceeded"})

        with patch("app.api.middleware.rate_limit.RATE_LIMIT_ENABLED", True):
            with patch("app.api.middleware.rate_limit.PROJECT_CREATE_LIMIT", 2):
                loop = asyncio.get_event_loop()
                loop.run_until_complete(middleware.dispatch(request, _noop_next))
                loop.run_until_complete(middleware.dispatch(request, _noop_next))
                response = loop.run_until_complete(middleware.dispatch(request, _noop_next))

        assert response.status_code == 429

    def test_non_project_path_not_rate_limited(self):
        """Non-project-creation paths must never trigger rate limiting."""
        from app.api.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=MagicMock())
        request = _make_request(path="/api/v1/workflow/proj-1/status", method="GET",
                                headers={"X-API-Key": "key-other"})

        with patch("app.api.middleware.rate_limit.RATE_LIMIT_ENABLED", True):
            with patch("app.api.middleware.rate_limit.PROJECT_CREATE_LIMIT", 0):
                # Limit is 0 — if middleware applied, would 429 immediately.
                response = asyncio.get_event_loop().run_until_complete(
                    middleware.dispatch(request, _noop_next)
                )
        assert response.status_code == 200

    def test_disabled_rate_limit_always_passes(self):
        """When RATE_LIMIT_ENABLED=false, all requests pass through."""
        from app.api.middleware.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(app=MagicMock())
        request = _make_request(headers={"X-API-Key": "key-disabled"})

        with patch("app.api.middleware.rate_limit.RATE_LIMIT_ENABLED", False):
            with patch("app.api.middleware.rate_limit.PROJECT_CREATE_LIMIT", 0):
                response = asyncio.get_event_loop().run_until_complete(
                    middleware.dispatch(request, _noop_next)
                )
        assert response.status_code == 200


class TestCheckProjectCreate:

    def setup_method(self):
        import app.api.middleware.rate_limit as rl
        with rl._lock:
            rl._store.clear()

    def test_raises_429_after_limit(self):
        """check_project_create() must raise HTTPException(429) after PROJECT_CREATE_LIMIT calls."""
        from app.api.middleware.rate_limit import check_project_create
        from fastapi import HTTPException

        with patch("app.api.middleware.rate_limit.RATE_LIMIT_ENABLED", True):
            with patch("app.api.middleware.rate_limit.PROJECT_CREATE_LIMIT", 2):
                check_project_create("key-create-1")
                check_project_create("key-create-1")
                with pytest.raises(HTTPException) as exc_info:
                    check_project_create("key-create-1")
        assert exc_info.value.status_code == 429

    def test_different_keys_have_separate_buckets(self):
        """Different API keys must not share rate limit buckets."""
        from app.api.middleware.rate_limit import check_project_create

        with patch("app.api.middleware.rate_limit.RATE_LIMIT_ENABLED", True):
            with patch("app.api.middleware.rate_limit.PROJECT_CREATE_LIMIT", 1):
                check_project_create("key-A")  # key-A at limit
                check_project_create("key-B")  # key-B should have its own bucket — no raise


# ---------------------------------------------------------------------------
# 5-7: RequestSizeLimitMiddleware
# ---------------------------------------------------------------------------

class TestRequestSizeLimitMiddleware:

    def _make_sized_request(self, content_length: int | None = None,
                            path: str = "/api/v1/projects"):
        request = MagicMock()
        request.url.path = path
        headers = {}
        if content_length is not None:
            headers["content-length"] = str(content_length)
        request.headers.get = lambda key, default=None: headers.get(key.lower(), default)
        return request

    def test_allows_request_under_limit(self):
        """Request with Content-Length under 50KB must pass through."""
        from app.api.middleware.request_size import RequestSizeLimitMiddleware

        middleware = RequestSizeLimitMiddleware(app=MagicMock(), max_body_bytes=51200)
        request = self._make_sized_request(content_length=1024)

        response = asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(request, _noop_next)
        )
        assert response.status_code == 200

    def test_returns_413_for_oversized_body(self):
        """Request with Content-Length > 50KB must be rejected with 413."""
        from app.api.middleware.request_size import RequestSizeLimitMiddleware

        middleware = RequestSizeLimitMiddleware(app=MagicMock(), max_body_bytes=51200)
        request = self._make_sized_request(content_length=51201)

        response = asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(request, _noop_next)
        )
        assert response.status_code == 413

    def test_passes_through_when_no_content_length(self):
        """Requests without Content-Length header must not be rejected."""
        from app.api.middleware.request_size import RequestSizeLimitMiddleware

        middleware = RequestSizeLimitMiddleware(app=MagicMock(), max_body_bytes=51200)
        request = self._make_sized_request(content_length=None)

        response = asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(request, _noop_next)
        )
        assert response.status_code == 200

    def test_413_response_contains_size_limit_in_detail(self):
        """413 response body must tell the caller the allowed limit."""
        from app.api.middleware.request_size import RequestSizeLimitMiddleware
        import json

        middleware = RequestSizeLimitMiddleware(app=MagicMock(), max_body_bytes=51200)
        request = self._make_sized_request(content_length=100_000)

        response = asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(request, _noop_next)
        )
        body = json.loads(response.body)
        assert "50" in body["detail"]  # "50 KB" appears in message


# ---------------------------------------------------------------------------
# 8-11: LoggingContextMiddleware
# ---------------------------------------------------------------------------

class TestLoggingContextMiddleware:

    def test_project_id_bound_from_workflow_path(self):
        """project_id must be extracted from /workflow/{project_id}/... paths."""
        from app.api.middleware.logging_context import (
            LoggingContextMiddleware,
            _project_id_var,
        )

        middleware = LoggingContextMiddleware(app=MagicMock())
        captured = {}

        async def _capturing_next(request):
            captured["project_id"] = _project_id_var.get("")
            return MagicMock(headers={})

        request = MagicMock()
        request.url.path = "/workflow/proj-abc123/status"
        request.headers.get = lambda k, d=None: d

        asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(request, _capturing_next)
        )
        assert captured["project_id"] == "proj-abc123"

    def test_request_id_bound_from_header(self):
        """Request-ID header must be preferred over auto-generated UUID."""
        from app.api.middleware.logging_context import (
            LoggingContextMiddleware,
            _request_id_var,
        )

        middleware = LoggingContextMiddleware(app=MagicMock())
        captured = {}

        async def _capturing_next(request):
            captured["request_id"] = _request_id_var.get("")
            return MagicMock(headers={})

        request = MagicMock()
        request.url.path = "/api/v1/projects"
        request.headers.get = lambda k, d=None: "my-req-id" if k == "X-Request-ID" else d

        asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(request, _capturing_next)
        )
        assert captured["request_id"] == "my-req-id"

    def test_contextvars_reset_after_response(self):
        """project_id and request_id must be empty after the request completes."""
        from app.api.middleware.logging_context import (
            LoggingContextMiddleware,
            _project_id_var,
            _request_id_var,
        )

        middleware = LoggingContextMiddleware(app=MagicMock())
        request = MagicMock()
        request.url.path = "/workflow/proj-xyz/run"
        request.headers.get = lambda k, d=None: d

        asyncio.get_event_loop().run_until_complete(
            middleware.dispatch(request, _noop_next)
        )
        # Outside the request context, vars should be empty
        assert _project_id_var.get("") == ""
        assert _request_id_var.get("") == ""

    def test_extract_project_id_workflow_path(self):
        """_extract_project_id() must match /workflow/{id}/... pattern."""
        from app.api.middleware.logging_context import _extract_project_id
        assert _extract_project_id("/workflow/abc-123/status") == "abc-123"

    def test_extract_project_id_projects_path(self):
        """_extract_project_id() must match /projects/{id} pattern."""
        from app.api.middleware.logging_context import _extract_project_id
        assert _extract_project_id("/api/v1/projects/proj-xyz/files") == "proj-xyz"

    def test_extract_project_id_unmatched_path(self):
        """_extract_project_id() must return empty string for unmatched paths."""
        from app.api.middleware.logging_context import _extract_project_id
        assert _extract_project_id("/health") == ""
        assert _extract_project_id("/docs") == ""

    def test_filter_installed_on_root_logger(self):
        """After middleware instantiation, root logger must have the context filter."""
        from app.api.middleware.logging_context import (
            LoggingContextMiddleware,
            _RequestContextFilter,
        )
        LoggingContextMiddleware(app=MagicMock())
        root_filters = logging.getLogger().filters
        assert any(isinstance(f, _RequestContextFilter) for f in root_filters)

    def test_filter_injects_project_id_into_log_record(self):
        """The logging filter must inject project_id from the contextvar into records."""
        from app.api.middleware.logging_context import (
            _RequestContextFilter,
            _project_id_var,
        )

        f = _RequestContextFilter()
        record = logging.makeLogRecord({"msg": "test"})
        token = _project_id_var.set("proj-filter-test")
        try:
            f.filter(record)
        finally:
            _project_id_var.reset(token)

        assert record.project_id == "proj-filter-test"
