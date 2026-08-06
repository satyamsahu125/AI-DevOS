"""R10 — Distributed tracing via OpenTelemetry.

Zero-cost when OTEL_ENDPOINT is not set: all calls resolve to no-op spans
and the heavy SDK imports are deferred until an endpoint is configured.

Usage:
    from app.observability.tracing import get_tracer, instrument_fastapi, configure_tracing

    # At startup (main.py / kernel.py):
    configure_tracing()

    # In agent/engine code:
    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("pipeline.run") as span:
        span.set_attribute("project_id", project_id)
        ...

Span naming convention:
    devos.pipeline.run          — full 3-phase pipeline for one project
    devos.stage.execute         — single stage (executor → reviewer → retry loop)
    devos.llm.call              — one LLM request (tokens, model, latency)
    devos.review.review         — reviewer evaluation
    devos.sprint.run            — one sprint (all its stages)

Architecture:
    - OTEL_ENDPOINT env var controls export destination (OTLP/gRPC)
    - OTEL_SERVICE_NAME defaults to "ai-devos"
    - No-op tracer is returned when endpoint is not configured
    - FastAPI auto-instrumentation is optional (call instrument_fastapi(app))
    - All spans carry project_id attribute for cross-service correlation
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)

_OTEL_ENDPOINT = os.getenv("OTEL_ENDPOINT", "").strip()
_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "ai-devos")
_OTEL_ENABLED = bool(_OTEL_ENDPOINT)

# Module-level tracer provider — set once by configure_tracing()
_tracer_provider: Any = None
_configured = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_tracing() -> None:
    """Initialize the OTel tracer provider.

    Safe to call multiple times — reconfigures only on the first call.
    No-op if OTEL_ENDPOINT is not set.
    """
    global _tracer_provider, _configured
    if _configured:
        return
    _configured = True

    if not _OTEL_ENABLED:
        logger.info(
            "[tracing] OTEL_ENDPOINT not set — distributed tracing disabled. "
            "Set OTEL_ENDPOINT=http://otel-collector:4317 to enable."
        )
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        resource = Resource.create({SERVICE_NAME: _SERVICE_NAME})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=_OTEL_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer_provider = provider
        logger.info(
            "[tracing] OpenTelemetry enabled: service=%s endpoint=%s",
            _SERVICE_NAME, _OTEL_ENDPOINT,
        )
    except ImportError as exc:
        logger.warning(
            "[tracing] opentelemetry-sdk not installed — tracing disabled: %s", exc
        )
    except Exception as exc:
        logger.warning(
            "[tracing] Failed to configure OpenTelemetry (non-fatal): %s", exc
        )


def get_tracer(name: str) -> Any:
    """Return an OTel tracer for *name*.

    Returns a real tracer when OTel is configured, otherwise a _NoOpTracer
    whose context managers are zero-cost.
    """
    if not _OTEL_ENABLED or _tracer_provider is None:
        return _NoOpTracer()
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except Exception:
        return _NoOpTracer()


def instrument_fastapi(app: Any) -> None:
    """Auto-instrument a FastAPI app with OpenTelemetry middleware.

    No-op if OTel is not enabled or the instrumentation package is missing.
    Must be called after configure_tracing() and before the first request.
    """
    if not _OTEL_ENABLED:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("[tracing] FastAPI auto-instrumentation active")
    except ImportError:
        logger.debug("[tracing] opentelemetry-instrumentation-fastapi not installed — skipping")
    except Exception as exc:
        logger.warning("[tracing] FastAPI instrumentation failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Convenience span context managers
# ---------------------------------------------------------------------------

@contextmanager
def pipeline_span(project_id: str, mode: str = "full") -> Generator[Any, None, None]:
    """Context manager for a full pipeline run span."""
    tracer = get_tracer("devos.pipeline")
    with tracer.start_as_current_span("devos.pipeline.run") as span:
        _set_attrs(span, project_id=project_id, mode=mode)
        try:
            yield span
        except Exception as exc:
            _record_exception(span, exc)
            raise


@contextmanager
def stage_span(project_id: str, stage_name: str, attempt: int = 1) -> Generator[Any, None, None]:
    """Context manager for a single stage execution span."""
    tracer = get_tracer("devos.stage")
    with tracer.start_as_current_span("devos.stage.execute") as span:
        _set_attrs(span, project_id=project_id, stage=stage_name, attempt=attempt)
        try:
            yield span
        except Exception as exc:
            _record_exception(span, exc)
            raise


@contextmanager
def llm_span(project_id: str, model: str, stage_name: str) -> Generator[Any, None, None]:
    """Context manager for a single LLM call span."""
    tracer = get_tracer("devos.llm")
    with tracer.start_as_current_span("devos.llm.call") as span:
        _set_attrs(span, project_id=project_id, model=model, stage=stage_name)
        try:
            yield span
        except Exception as exc:
            _record_exception(span, exc)
            raise


@contextmanager
def sprint_span(project_id: str, sprint_number: int) -> Generator[Any, None, None]:
    """Context manager for a single sprint execution span."""
    tracer = get_tracer("devos.sprint")
    with tracer.start_as_current_span("devos.sprint.run") as span:
        _set_attrs(span, project_id=project_id, sprint_number=sprint_number)
        try:
            yield span
        except Exception as exc:
            _record_exception(span, exc)
            raise


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_attrs(span: Any, **kwargs: Any) -> None:
    """Set span attributes — no-op if span is a _NoOpSpan."""
    if isinstance(span, _NoOpSpan):
        return
    try:
        for key, value in kwargs.items():
            if value is not None:
                span.set_attribute(f"devos.{key}", str(value))
    except Exception:
        pass


def _record_exception(span: Any, exc: Exception) -> None:
    """Record exception on span — no-op if span is a _NoOpSpan."""
    if isinstance(span, _NoOpSpan):
        return
    try:
        span.record_exception(exc)
        span.set_status(span.status.__class__(2, str(exc)))  # StatusCode.ERROR = 2
    except Exception:
        pass


# ---------------------------------------------------------------------------
# No-op tracer — zero overhead when OTel is disabled
# ---------------------------------------------------------------------------

class _NoOpSpan:
    """Minimal span stub — no allocations, no overhead."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ARG002
        pass

    def record_exception(self, exc: Exception) -> None:  # noqa: ARG002
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    """Minimal tracer stub that returns _NoOpSpan from start_as_current_span."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:  # noqa: ARG002
        return _NoOpSpan()
