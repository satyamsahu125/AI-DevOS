from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config.env_writer import upsert_env_values
from ..llm.manager import LLMManager
from .dependencies import get_llm_manager

router = APIRouter()

_ENV_KEY_BY_FIELD = {
    "provider":        "LLM_PROVIDER",
    "model":           "LLM_MODEL",
    "bedrock_api_key": "BEDROCK_API_KEY",
    "bedrock_region":  "BEDROCK_REGION",
    "claude_api_key":  "CLAUDE_API_KEY",
    "gemini_api_key":  "GEMINI_API_KEY",
}


class LLMSettingsUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    bedrock_api_key: str | None = None
    bedrock_region: str | None = None
    claude_api_key: str | None = None
    gemini_api_key: str | None = None


@router.get("/api/settings/llm")
@router.get("/settings/llm")
def get_llm_settings(manager: LLMManager = Depends(get_llm_manager)) -> dict:
    """Report the active provider/model. API keys are never echoed, only whether they are set."""
    s = manager._settings.llm
    return {
        "provider": s.provider,
        "model": s.model,
        "base_url": s.base_url,
        "bedrock_region": s.bedrock_region,
        "bedrock_api_key_set": bool(s.bedrock_api_key),
        "claude_api_key_set": bool(getattr(s, "claude_api_key", "")),
        "gemini_api_key_set": bool(getattr(s, "gemini_api_key", "")),
    }


@router.post("/api/settings/llm")
@router.post("/settings/llm")
def update_llm_settings(
    update: LLMSettingsUpdate,
    manager: LLMManager = Depends(get_llm_manager),
) -> dict:
    """Switch the active provider/model at runtime and persist to backend/.env."""
    fields = update.model_dump(exclude_none=True)
    env_values = {
        _ENV_KEY_BY_FIELD[k]: v
        for k, v in fields.items()
        if k in _ENV_KEY_BY_FIELD
    }
    if env_values:
        upsert_env_values(env_values)

    provider = fields.pop("provider", None)
    model = fields.pop("model", None)
    manager.reconfigure(provider=provider, model=model, **fields)
    return get_llm_settings(manager)


@router.get("/api/settings/providers")
@router.get("/settings/providers")
def list_providers(manager: LLMManager = Depends(get_llm_manager)) -> dict:
    """Catalog of selectable providers for the Settings UI."""
    ollama_models: list[str] = []
    try:
        if manager.configured_provider.lower() in {"ollama", "default"}:
            ollama_models = manager._provider.supported_models()
    except Exception:
        pass

    return {
        "providers": [
            {
                "id": "ollama",
                "label": "Ollama (local)",
                "requires_api_key": False,
                "models": ollama_models,
                "default_model": "qwen2.5-coder:7b",
                "notes": "Local inference. Fast for small models; limited context window.",
            },
            {
                "id": "claude",
                "label": "Anthropic Claude",
                "requires_api_key": True,
                "api_key_field": "claude_api_key",
                # Use full date-stamped model IDs — shorthand aliases (e.g.
                # "claude-sonnet-4-5" without a date) return HTTP 404 from
                # the Anthropic Messages API.
                "models": [
                    "claude-3-5-sonnet-20241022",
                    "claude-3-5-haiku-20241022",
                    "claude-3-opus-20240229",
                    "claude-haiku-4-5-20251001",
                ],
                "default_model": "claude-3-5-sonnet-20241022",
                "notes": "Best JSON quality. Recommended for Architect/BackendDev stages. Use full date-stamped model IDs.",
            },
            {
                "id": "gemini",
                "label": "Google Gemini",
                "requires_api_key": True,
                "api_key_field": "gemini_api_key",
                "models": [
                    "gemini-2.0-flash",
                    "gemini-2.0-flash-lite",
                    "gemini-1.5-flash",
                    "gemini-1.5-pro",
                ],
                "default_model": "gemini-2.0-flash",
                "notes": "1M token context, fast, free tier available. Strong JSON mode.",
            },
            {
                "id": "bedrock",
                "label": "AWS Bedrock",
                "requires_api_key": True,
                "api_key_field": "bedrock_api_key",
                "models": [],
                "default_model": "",
                "notes": "Enterprise / private deployment. Model ID from your Bedrock catalog.",
            },
        ]
    }
