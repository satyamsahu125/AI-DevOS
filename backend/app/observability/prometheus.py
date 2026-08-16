"""Phase 6 — Prometheus metrics for FastAPI.

Exposes a /metrics endpoint using prometheus-fastapi-instrumentator.
Enabled by default (PROMETHEUS_ENABLED=true); set PROMETHEUS_ENABLED=false
to disable in environments where Prometheus scraping is not configured.

Follows the same guard pattern as observability/tracing.py:
  - Safe to call regardless of whether the package is installed.
  - No-op with a WARNING log when disabled or the package is missing.

Usage (main.py):
    from .observability.prometheus import instrument_prometheus
    instrument_prometheus(app)   # called after app middleware is wired
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PROMETHEUS_ENABLED: bool = (
    os.getenv("PROMETHEUS_ENABLED", "true").lower() in ("true", "1", "yes")
)


def instrument_prometheus(app: Any) -> None:
    """Wire Prometheus instrumentation onto a FastAPI app.

    Adds a ``/metrics`` endpoint that Prometheus can scrape.  The endpoint
    is registered on *app* itself (not as middleware) so it bypasses the API
    key middleware automatically — scrapers do not carry user credentials.

    No-op when:
      - PROMETHEUS_ENABLED=false (opt-out)
      - ``prometheus-fastapi-instrumentator`` is not installed

    Parameters
    ----------
    app:
        The FastAPI application instance returned by ``create_application()``.
        Must be called after all middleware and routes are registered.
    """
    if not _PROMETHEUS_ENABLED:
        logger.info(
            "[prometheus] PROMETHEUS_ENABLED=false — Prometheus metrics disabled."
        )
        return

    try:
        from prometheus_fastapi_instrumentator import Instrumentator

        Instrumentator().instrument(app).expose(app)
        logger.info("[prometheus] /metrics endpoint registered")
    except ImportError:
        logger.warning(
            "[prometheus] prometheus-fastapi-instrumentator not installed — "
            "metrics endpoint unavailable. Run: pip install prometheus-fastapi-instrumentator"
        )
    except Exception as exc:
        logger.warning(
            "[prometheus] Failed to register /metrics endpoint (non-fatal): %s", exc
        )
