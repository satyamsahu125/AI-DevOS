from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api.exception_handler import application_exception_handler
from .api.router import api_router
from .kernel.kernel import AIKernel
from .shared.exceptions.base import ApplicationException

kernel = AIKernel()


@asynccontextmanager
async def lifespan(app: FastAPI):
    kernel.start()
    try:
        yield
    finally:
        kernel.stop()


def create_application() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(api_router)
    app.add_exception_handler(ApplicationException, application_exception_handler)
    return app


app = create_application()
