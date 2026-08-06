from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .models import Settings

logger = logging.getLogger(__name__)

# PyYAML is optional — the system runs entirely from .env when absent.
try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False


class ConfigurationLoader:
    """Loads Settings from environment variables (via .env), with an optional
    config.yaml as a lower-priority baseline.

    Priority (highest → lowest):
      1. Process environment / .env file
      2. config.yaml  (optional — system works without it)
      3. Pydantic model defaults in models.py

    This is pure 12-factor: the .env file is the only file you need to edit
    to change providers, models, or any runtime setting.
    """

    def __init__(self) -> None:
        self._config_paths = [
            Path(__file__).resolve().parents[2] / "config" / "config.yaml",
            Path(__file__).resolve().parents[1] / "config" / "config.yaml",
        ]
        self._load_dotenv()

    def _load_dotenv(self) -> None:
        """Load backend/.env into the process environment (python-dotenv, if installed)."""
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
        """Return Settings built from env vars + optional YAML baseline."""
        payload: dict[str, Any] = {}

        # Optional YAML baseline (lower priority than env vars)
        if _YAML_AVAILABLE:
            config_path = path
            if config_path is None:
                config_path = next(
                    (c for c in self._config_paths if c.exists()), None
                )
            if config_path is not None and config_path.exists():
                try:
                    payload = _yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                    logger.debug("config.yaml loaded: path=%s", config_path)
                except Exception as exc:  # pragma: no cover
                    logger.warning("config.yaml parse error (ignored): %s", exc)
                    payload = {}

        self._apply_env_overrides(payload)
        return Settings(**payload)

    def _apply_env_overrides(self, payload: dict[str, Any]) -> None:
        """Apply .env / environment variables on top of payload (in place).

        Only the variables documented in backend/.env.example are consulted.
        Anything else in os.environ is ignored.
        """
        llm = dict(payload.get("llm") or {})

        # ── Ollama-specific (only applied when provider=ollama) ───────────────
        if os.environ.get("OLLAMA_BASE_URL"):
            llm["base_url"] = os.environ["OLLAMA_BASE_URL"]
            llm["ollama_base_url"] = os.environ["OLLAMA_BASE_URL"]
        if os.environ.get("OLLAMA_MODEL"):
            llm["model"] = os.environ["OLLAMA_MODEL"]

        # ── Generic (any provider) — applied after Ollama so they win ────────
        # LLM_PROVIDER / LLM_MODEL always override provider-specific keys above
        if os.environ.get("LLM_PROVIDER"):
            llm["provider"] = os.environ["LLM_PROVIDER"]
        if os.environ.get("LLM_MODEL"):
            llm["model"] = os.environ["LLM_MODEL"]

        # OLLAMA_TEMPERATURE / OLLAMA_MAX_TOKENS only apply when provider=ollama
        # so they don't silently cap cloud providers (Bedrock/Gemini/Claude).
        active_provider = llm.get("provider", "ollama")
        if active_provider == "ollama":
            if os.environ.get("OLLAMA_TEMPERATURE"):
                llm["temperature"] = float(os.environ["OLLAMA_TEMPERATURE"])
            if os.environ.get("OLLAMA_MAX_TOKENS"):
                llm["max_tokens"] = int(os.environ["OLLAMA_MAX_TOKENS"])

        # Generic overrides — apply to any provider (highest priority)
        if os.environ.get("LLM_TEMPERATURE"):
            llm["temperature"] = float(os.environ["LLM_TEMPERATURE"])
        if os.environ.get("LLM_MAX_TOKENS"):
            llm["max_tokens"] = int(os.environ["LLM_MAX_TOKENS"])

        # ── Bedrock ───────────────────────────────────────────────────────────
        if os.environ.get("BEDROCK_API_KEY"):
            llm["bedrock_api_key"] = os.environ["BEDROCK_API_KEY"]
        if os.environ.get("BEDROCK_REGION"):
            llm["bedrock_region"] = os.environ["BEDROCK_REGION"]

        # ── Claude (direct Anthropic API) ─────────────────────────────────────
        if os.environ.get("CLAUDE_API_KEY"):
            llm["claude_api_key"] = os.environ["CLAUDE_API_KEY"]

        # ── Gemini ────────────────────────────────────────────────────────────
        if os.environ.get("GEMINI_API_KEY"):
            llm["gemini_api_key"] = os.environ["GEMINI_API_KEY"]

        if llm:
            payload["llm"] = llm

        # ── Runtime ──────────────────────────────────────────────────────────
        runtime = dict(payload.get("runtime") or {})
        if os.environ.get("LOG_LEVEL"):
            runtime["log_level"] = os.environ["LOG_LEVEL"]
        if os.environ.get("MAX_RETRIES"):
            runtime["retry_limit"] = int(os.environ["MAX_RETRIES"])
        if runtime:
            payload["runtime"] = runtime

        # ── Storage ──────────────────────────────────────────────────────────
        if os.environ.get("KNOWLEDGE_DB"):
            payload["knowledge_db"] = os.environ["KNOWLEDGE_DB"]
        if os.environ.get("LEARNING_DB"):
            payload["learning_db"] = os.environ["LEARNING_DB"]
        if os.environ.get("LESSONS_DB"):
            payload["lessons_db"] = os.environ["LESSONS_DB"]

        # ── Sprint retry limits ───────────────────────────────────────────────
        if os.environ.get("MAX_DEV_REVIEW_ITERATIONS"):
            payload.setdefault("sprint_retry", {})["max_dev_review_iterations"] = int(os.environ["MAX_DEV_REVIEW_ITERATIONS"])
        if os.environ.get("MAX_QA_ITERATIONS"):
            payload.setdefault("sprint_retry", {})["max_qa_iterations"] = int(os.environ["MAX_QA_ITERATIONS"])
        if os.environ.get("MAX_SPEC_FIX_ITERATIONS"):
            payload.setdefault("sprint_retry", {})["max_spec_fix_iterations"] = int(os.environ["MAX_SPEC_FIX_ITERATIONS"])
