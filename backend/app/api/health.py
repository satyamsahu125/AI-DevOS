from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response

from ..llm.manager import LLMManager
from ..memory.manager import MemoryManager
from .dependencies import get_llm_manager, get_memory_manager

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/ready")
def ready(
    response: Response,
    llm_manager: LLMManager = Depends(get_llm_manager),
    memory_manager: MemoryManager = Depends(get_memory_manager),
) -> dict:
    """Real readiness probe: is Ollama reachable, is the configured model loaded, is the database reachable."""
    try:
        provider_health = llm_manager.health()
    except Exception:
        response.status_code = 503
        return {
            "status": "degraded",
            "ollama": "unreachable",
            "message": "Start Ollama: ollama serve",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    model_available = llm_manager.is_model_available() if provider_health.reachable else False

    try:
        memory_manager.load("__health_check__", "__ping__")
        database_ok = True
    except Exception:
        database_ok = False

    is_ready = provider_health.reachable and database_ok
    response.status_code = 200 if is_ready else 503

    res = {
        "status": "ready" if is_ready else "degraded",
        "ollama": "reachable" if provider_health.reachable else "unreachable",
        "model": llm_manager.configured_model,
        "model_available": model_available,
        "database": "connected" if database_ok else "error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not provider_health.reachable:
        res["message"] = "Start Ollama: ollama serve"
    return res
