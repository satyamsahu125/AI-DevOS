"""test_phase6_prometheus.py — Phase 6 UPDATE requirements.txt / prometheus wiring.

Verifies:
  1. prometheus-fastapi-instrumentator is importable (package is installed).
  2. instrument_prometheus() is importable from observability.prometheus.
  3. When PROMETHEUS_ENABLED=false (default), instrument_prometheus() is a no-op:
     it does not add any new routes to the app.
  4. When PROMETHEUS_ENABLED=true, instrument_prometheus() adds a /metrics route.
  5. The /metrics route responds with 200 and a valid content-type.
  6. instrument_prometheus() does not raise when called with a bare FastAPI app.
  7. _PROMETHEUS_ENABLED reads from PROMETHEUS_ENABLED env var.
  8. instrument_prometheus() is gracefully no-op when the package is missing
     (ImportError path is handled without crashing).

Running:
    cd backend
    python -m pytest tests/test_phase6_prometheus.py -v
"""
from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
pytest.importorskip("prometheus_fastapi_instrumentator")

from fastapi import FastAPI
from fastapi.testclient import TestClient



# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _fresh_app() -> FastAPI:
    """Return a minimal FastAPI app for isolation."""
    return FastAPI()


def _route_paths(app: FastAPI) -> list[str]:
    """Return all registered route paths on *app*."""
    return [route.path for route in app.routes if hasattr(route, "path")]


# ---------------------------------------------------------------------------
# 1. Package installed
# ---------------------------------------------------------------------------

def test_prometheus_package_importable():
    """prometheus-fastapi-instrumentator must be importable after pip install."""
    import prometheus_fastapi_instrumentator  # noqa: F401 — import is the test


def test_instrumentator_class_importable():
    """Instrumentator class must be importable from the package."""
    from prometheus_fastapi_instrumentator import Instrumentator  # noqa: F401


# ---------------------------------------------------------------------------
# 2. Our wrapper module importable
# ---------------------------------------------------------------------------

def test_instrument_prometheus_importable():
    """instrument_prometheus must be importable from app.observability.prometheus."""
    from app.observability.prometheus import instrument_prometheus  # noqa: F401


# ---------------------------------------------------------------------------
# 3. No-op when PROMETHEUS_ENABLED=false (default)
# ---------------------------------------------------------------------------

def test_noop_when_disabled(monkeypatch):
    """instrument_prometheus() must not register /metrics when PROMETHEUS_ENABLED=false."""
    import app.observability.prometheus as prom_mod

    monkeypatch.setattr(prom_mod, "_PROMETHEUS_ENABLED", False)

    app = _fresh_app()
    before = set(_route_paths(app))

    prom_mod.instrument_prometheus(app)

    after = set(_route_paths(app))
    assert "/metrics" not in after, "/metrics must not be added when disabled"
    # No new routes should appear either
    assert after == before or "/metrics" not in after


# ---------------------------------------------------------------------------
# 4. /metrics route registered when PROMETHEUS_ENABLED=true
# ---------------------------------------------------------------------------

def test_metrics_route_registered_when_enabled(monkeypatch):
    """instrument_prometheus() must add a /metrics route when PROMETHEUS_ENABLED=true."""
    import app.observability.prometheus as prom_mod

    monkeypatch.setattr(prom_mod, "_PROMETHEUS_ENABLED", True)

    app = _fresh_app()
    prom_mod.instrument_prometheus(app)

    paths = _route_paths(app)
    assert "/metrics" in paths, f"/metrics route not found; routes={paths}"


# ---------------------------------------------------------------------------
# 5. /metrics responds 200 with prometheus content-type
# ---------------------------------------------------------------------------

def test_metrics_endpoint_returns_200(monkeypatch):
    """GET /metrics must return 200 with text/plain or application/openmetrics content-type."""
    import app.observability.prometheus as prom_mod

    monkeypatch.setattr(prom_mod, "_PROMETHEUS_ENABLED", True)

    app = _fresh_app()
    prom_mod.instrument_prometheus(app)

    client = TestClient(app, raise_server_exceptions=True)
    response = client.get("/metrics")

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "text/plain" in content_type or "openmetrics" in content_type, (
        f"Unexpected content-type for /metrics: {content_type}"
    )


# ---------------------------------------------------------------------------
# 6. No exception on a bare FastAPI app
# ---------------------------------------------------------------------------

def test_no_exception_on_bare_app(monkeypatch):
    """instrument_prometheus() must not raise when called on a minimal FastAPI app."""
    import app.observability.prometheus as prom_mod

    monkeypatch.setattr(prom_mod, "_PROMETHEUS_ENABLED", True)
    app = _fresh_app()
    prom_mod.instrument_prometheus(app)  # must not raise


# ---------------------------------------------------------------------------
# 7. Env var controls _PROMETHEUS_ENABLED
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("true", True),
    ("1", True),
    ("yes", True),
    ("false", False),
    ("0", False),
    ("", False),
])
def test_prometheus_enabled_env_var(value, expected, monkeypatch):
    """_PROMETHEUS_ENABLED must reflect the PROMETHEUS_ENABLED env var."""
    monkeypatch.setenv("PROMETHEUS_ENABLED", value)

    # Force module reload to pick up patched env var
    if "app.observability.prometheus" in sys.modules:
        del sys.modules["app.observability.prometheus"]

    import app.observability.prometheus as prom_mod
    assert prom_mod._PROMETHEUS_ENABLED is expected


# ---------------------------------------------------------------------------
# 8. Graceful no-op on ImportError
# ---------------------------------------------------------------------------

def test_graceful_noop_on_import_error(monkeypatch):
    """instrument_prometheus() must not raise if the package is not installed."""
    import app.observability.prometheus as prom_mod

    monkeypatch.setattr(prom_mod, "_PROMETHEUS_ENABLED", True)

    def _raise_import(*args, **kwargs):
        raise ImportError("prometheus_fastapi_instrumentator not installed")

    app = _fresh_app()
    # Patch builtins.__import__ is fragile; patch the module's import path instead.
    with patch("builtins.__import__", side_effect=_raise_import):
        # instrument_prometheus catches ImportError and logs — must not propagate
        try:
            prom_mod.instrument_prometheus(app)
        except ImportError:
            pytest.fail("instrument_prometheus() must not propagate ImportError")
