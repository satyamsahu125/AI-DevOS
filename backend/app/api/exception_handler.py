from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from ..shared.exceptions.base import ApplicationException


async def application_exception_handler(request: Request, exc: ApplicationException) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})
