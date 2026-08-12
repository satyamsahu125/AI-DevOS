# ── Load .env FIRST ────────────────────────────────────────────────────────────
# Several modules read os.getenv() at module-level (AUTH_ENABLED, JWT_SECRET_KEY,
# VALID_API_KEYS, etc.). If load_dotenv() runs after those modules are imported,
# the env vars from .env are never seen.  Loading here — before every other import
# — guarantees .env is in os.environ before any module reads it.
import os as _os
from pathlib import Path as _Path
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _Path(__file__).resolve().parents[1] / ".env"
    if _env_file.exists():
        _load_dotenv(_env_file, override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on real env vars
# ── End early .env load ────────────────────────────────────────────────────────

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.openapi.utils import get_openapi

from .api.exception_handler import application_exception_handler
from .api.middleware.auth import APIKeyMiddleware
from .api.middleware.rate_limit import RateLimitMiddleware
from .api.middleware.request_size import RequestSizeLimitMiddleware
from .api.middleware.logging_context import LoggingContextMiddleware
from .api.router import api_router
from .events.broadcaster import broadcaster
from .kernel.kernel import AIKernel
from .observability.logging import configure_logging
from .observability.tracing import configure_tracing, instrument_fastapi
from .observability.prometheus import instrument_prometheus
from .shared.exceptions.base import ApplicationException

# Phase 6: configure structured logging before anything else runs
configure_logging()
# R10: configure distributed tracing (no-op when OTEL_ENDPOINT is not set)
configure_tracing()

kernel = AIKernel()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # FIX-B: Capture the uvicorn event loop so the broadcaster can schedule
    # WebSocket sends from FastAPI BackgroundTask threads (which have no loop).
    broadcaster.bind_loop(asyncio.get_running_loop())
    kernel.start()
    try:
        yield
    finally:
        kernel.stop()


def create_application() -> FastAPI:
    app = FastAPI(
        title="AI DevOS",
        version="2.0.0",
        description="Autonomous software engineering platform",
        lifespan=lifespan,
    )

    # Add Bearer token security scheme so Swagger UI shows the Authorize button
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema.setdefault("components", {})
        schema["components"]["securitySchemes"] = {
            "bearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
            }
        }
        schema["security"] = [{"bearerAuth": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    # CORS — must be added before any auth middleware so preflight OPTIONS
    # requests are handled before they hit the auth layer.
    # In production set ALLOWED_ORIGINS to the exact frontend origin(s).
    _raw_origins = _os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    _allow_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Phase 6: API key authentication middleware
    # Reads VALID_API_KEYS from env; disabled (pass-through) when not set.
    app.add_middleware(APIKeyMiddleware)

    # Phase 6: Rate limiting — 10 project creates/minute per API key.
    # Disabled by default (RATE_LIMIT_ENABLED=false); enable in production.
    app.add_middleware(RateLimitMiddleware)

    # Phase 6: Request body size limit — reject bodies > 50 KB.
    # Prevents oversized descriptions from being embedded in every LLM prompt.
    app.add_middleware(RequestSizeLimitMiddleware)

    # Phase 6: Per-request structured logging context.
    # Binds request_id and project_id to every log line for the request lifetime.
    app.add_middleware(LoggingContextMiddleware)

    # R10: FastAPI auto-instrumentation (no-op when OTEL_ENDPOINT is not set)
    instrument_fastapi(app)

    # Phase 6: Prometheus /metrics endpoint.
    # Disabled when PROMETHEUS_ENABLED=false (default); enable in production.
    instrument_prometheus(app)

    app.include_router(api_router)
    app.add_exception_handler(ApplicationException, application_exception_handler)

    @app.get("/ready")
    def top_ready(response: Response):
        from .api.health import ready
        from .api.dependencies import get_llm_manager, get_memory_manager, get_container
        c = get_container()
        return ready(response, llm_manager=c.llm_manager, memory_manager=c.memory_manager)

    return app


app = create_application()
