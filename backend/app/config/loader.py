from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from .models import Settings

logger = logging.getLogger(__name__)


class ConfigurationLoader:
    """Loads Settings from config.yaml, with a small set of environment-variable overrides on top.

    Environment variables (see backend/.env) take precedence over
    config.yaml, matching typical 12-factor practice: the yaml file holds
    checked-in defaults, the environment holds per-deployment overrides.
    Only the variables backend/.env documents are consulted; anything else
    in os.environ is ignored.
    """

    def __init__(self) -> None:
        self._config_paths = [
            Path(__file__).resolve().parents[2] / "config" / "config.yaml",
            Path(__file__).resolve().parents[1] / "config" / "config.yaml",
        ]
        self._load_dotenv()

    def _load_dotenv(self) -> None:
        """Load backend/.env into the process environment, if python-dotenv and the file are both present."""
        try:
            from dotenv import load_dotenv
        except ImportError:
            logger.debug("python-dotenv not installed; skipping .env load")
            return
        env_path = Path(__file__).resolve().parents[2] / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
            logger.debug(".env loaded: path=%s", env_path)

    def load(self, path: Path | None = None) -> Settings:
        """Load Settings from config_path (or the first existing default location), then apply env overrides."""
        config_path = path
        if config_path is None:
            config_path = next((candidate for candidate in self._config_paths if candidate.exists()), self._config_paths[0])
        payload: dict[str, Any] = {}
        if config_path.exists():
            payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        self._apply_env_overrides(payload)
        return Settings(**payload)

    def _apply_env_overrides(self, payload: dict[str, Any]) -> None:
        """Apply the documented environment-variable overrides (see backend/.env) on top of payload, in place."""
        llm = dict(payload.get("llm") or {})
        if os.environ.get("OLLAMA_BASE_URL"):
            # Store as both base_url (legacy) AND ollama_base_url (preferred).
            # The factory now ignores base_url for Claude/Gemini so this no
            # longer bleeds the Ollama localhost address into cloud providers.
            llm["base_url"] = os.environ["OLLAMA_BASE_URL"]
            llm["ollama_base_url"] = os.environ["OLLAMA_BASE_URL"]
        if os.environ.get("OLLAMA_MODEL"):
            llm["model"] = os.environ["OLLAMA_MODEL"]
        if os.environ.get("OLLAMA_TEMPERATURE"):
            llm["temperature"] = float(os.environ["OLLAMA_TEMPERATURE"])
        if os.environ.get("OLLAMA_MAX_TOKENS"):
            llm["max_tokens"] = int(os.environ["OLLAMA_MAX_TOKENS"])
        if os.environ.get("LLM_PROVIDER"):
            llm["provider"] = os.environ["LLM_PROVIDER"]
        if os.environ.get("LLM_MODEL"):
            llm["model"] = os.environ["LLM_MODEL"]
        if os.environ.get("BEDROCK_API_KEY"):
            llm["bedrock_api_key"] = os.environ["BEDROCK_API_KEY"]
        if os.environ.get("BEDROCK_REGION"):
            llm["bedrock_region"] = os.environ["BEDROCK_REGION"]
        if os.environ.get("CLAUDE_API_KEY"):
            llm["claude_api_key"] = os.environ["CLAUDE_API_KEY"]
        if os.environ.get("GEMINI_API_KEY"):
            llm["gemini_api_key"] = os.environ["GEMINI_API_KEY"]
        if llm:
            payload["llm"] = llm

        runtime = dict(payload.get("runtime") or {})
        if os.environ.get("LOG_LEVEL"):
            runtime["log_level"] = os.environ["LOG_LEVEL"]
        if os.environ.get("MAX_RETRIES"):
            runtime["retry_limit"] = int(os.environ["MAX_RETRIES"])
        if runtime:
            payload["runtime"] = runtime

        if os.environ.get("KNOWLEDGE_DB"):
            payload["knowledge_db"] = os.environ["KNOWLEDGE_DB"]
        if os.environ.get("LEARNING_DB"):
            payload["learning_db"] = os.environ["LEARNING_DB"]
