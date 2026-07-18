from fastapi import APIRouter

from .health import router as health_router
from .project import router as project_router
from .workflow import router as workflow_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(project_router)
api_router.include_router(workflow_router)
