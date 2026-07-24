from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config.env_writer import upsert_env_values
from ..llm.manager import LLMManager
from .dependencies import get_llm_manager

router = APIRouter()

_ENV_KEY_BY_FIELD = {
    "provider": "LLM_PROVIDER",
    "model": "LLM_MODEL",
    "bedrock_api_key": "BEDROCK_API_KEY",
    "bedrock_region": "BEDROCK_REGION",
}


class LLMSettingsUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    bedrock_api_key: str | None = None
    bedrock_region: str | None = None


@router.get("/settings/llm")
def get_llm_settings(manager: LLMManager = Depends(get_llm_manager)) -> dict:
    """Report the active provider/model -- the Bedrock key itself is never echoed back, only whether one is set."""
    settings = manager._settings.llm
    return {
        "provider": settings.provider,
        "model": settings.model,
        "base_url": settings.base_url,
        "bedrock_region": settings.bedrock_region,
        "bedrock_api_key_set": bool(settings.bedrock_api_key),
    }


@router.post("/settings/llm")
def update_llm_settings(update: LLMSettingsUpdate, manager: LLMManager = Depends(get_llm_manager)) -> dict:
    """Switch the active provider/model at runtime and persist the choice (plus any Bedrock key) to backend/.env."""
    fields = update.model_dump(exclude_none=True)
    env_values = {_ENV_KEY_BY_FIELD[key]: value for key, value in fields.items() if key in _ENV_KEY_BY_FIELD}
    if env_values:
        upsert_env_values(env_values)

    provider = fields.pop("provider", None)
    model = fields.pop("model", None)
    manager.reconfigure(provider=provider, model=model, **fields)
    return get_llm_settings(manager)


@router.get("/settings/providers")
def list_providers(manager: LLMManager = Depends(get_llm_manager)) -> dict:
    """Static catalog of selectable providers for the Settings UI.

    Bedrock has no unauthenticated model-listing endpoint, so its model
    field is free text in the UI -- pick the exact model id from your
    account's Bedrock model catalog (e.g. Qwen3 Coder 480B's listed id).
    """
    ollama_models: list[str] = []
    try:
        if manager.configured_provider.lower() in {"ollama", "default"}:
            ollama_models = manager._provider.supported_models()
    except Exception:
        ollama_models = []

    return {
        "providers": [
            {
                "id": "ollama",
                "label": "Ollama (local)",
                "models": ollama_models,
                "requires_api_key": False,
            },
            {
                "id": "bedrock",
                "label": "AWS Bedrock",
                "models": [],
                "requires_api_key": True,
            },
        ]
    }
