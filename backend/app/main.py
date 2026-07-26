import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from .api.exception_handler import application_exception_handler
from .api.router import api_router
from .events.broadcaster import broadcaster
from .kernel.kernel import AIKernel
from .shared.exceptions.base import ApplicationException

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
