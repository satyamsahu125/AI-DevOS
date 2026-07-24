from fastapi import APIRouter

from .agents import router as agents_router
from .artifacts import router as artifacts_router
from .files import router as files_router
from .health import router as health_router
from .logs import router as logs_router
from .memory import router as memory_router
from .project import router as project_router
from .settings import router as settings_router
from .workflow import router as workflow_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(project_router)
api_router.include_router(workflow_router)
api_router.include_router(artifacts_router)
api_router.include_router(agents_router)
api_router.include_router(memory_router)
api_router.include_router(files_router)
api_router.include_router(logs_router)
api_router.include_router(settings_router)
