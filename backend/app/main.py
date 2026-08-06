import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .api.exception_handler import application_exception_handler
from .api.middleware.auth import APIKeyMiddleware
from .api.router import api_router
from .events.broadcaster import broadcaster
from .kernel.kernel import AIKernel
from .observability.logging import configure_logging
from .observability.tracing import configure_tracing, instrument_fastapi
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
    app = FastAPI(lifespan=lifespan)

    # Phase 6: API key authentication middleware
    # Reads VALID_API_KEYS from env; disabled (pass-through) when not set.
    app.add_middleware(APIKeyMiddleware)

    # R10: FastAPI auto-instrumentation (no-op when OTEL_ENDPOINT is not set)
    instrument_fastapi(app)

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
