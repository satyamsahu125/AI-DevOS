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
    """Readiness probe: is the configured LLM provider reachable, model loaded, database up."""
    provider = llm_manager.configured_provider
    model    = llm_manager.configured_model

    try:
        provider_health = llm_manager.health()
    except Exception:
        response.status_code = 503
        return {
            "status": "degraded",
            "provider": provider,
            "provider_status": "unreachable",
            "model": model,
            "model_available": False,
            "database": "unknown",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": _provider_hint(provider),
        }

    model_available = llm_manager.is_model_available() if provider_health.reachable else False

    try:
        memory_manager.load("__health_check__", "__ping__")
        database_ok = True
    except Exception:
        database_ok = False

    is_ready = provider_health.reachable and database_ok
    response.status_code = 200 if is_ready else 503

    res: dict = {
        "status": "ready" if is_ready else "degraded",
        "provider": provider,
        "provider_status": "reachable" if provider_health.reachable else "unreachable",
        "model": model,
        "model_available": model_available,
        "database": "connected" if database_ok else "error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if not provider_health.reachable:
        res["message"] = _provider_hint(provider)
    return res


def _provider_hint(provider: str) -> str:
    """Return a human-readable hint for how to fix connectivity for the given provider."""
    hints = {
        "ollama":  "Start Ollama: ollama serve",
        "bedrock": "Check BEDROCK_API_KEY and BEDROCK_REGION in .env",
        "claude":  "Check CLAUDE_API_KEY in .env",
        "gemini":  "Check GEMINI_API_KEY in .env",
    }
    return hints.get(provider.lower(), f"Check {provider.upper()} credentials in .env")
