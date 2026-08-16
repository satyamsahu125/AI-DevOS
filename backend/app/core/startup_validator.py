"""Startup pre-flight validator.

Checks the environment for misconfiguration before the application begins
serving traffic.  All checks are purely local — no network calls are made.

Usage (main.py lifespan):
    from .core.startup_validator import StartupValidator

    errors = StartupValidator().validate()
    if errors:
        for err in errors:
            logger.critical("[startup] %s", err)
        raise RuntimeError(
            f"Startup validation failed ({len(errors)} error(s)). "
            "Fix the issues above and restart."
        )
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider → required env var name (None = no key required, e.g. Ollama)
# ---------------------------------------------------------------------------
_PROVIDER_KEY_ENVS: dict[str, str | None] = {
    "ollama":  None,
    "claude":  "CLAUDE_API_KEY",
    "openai":  "OPENAI_API_KEY",
    "gemini":  "GEMINI_API_KEY",
    "bedrock": "BEDROCK_API_KEY",
    "groq":    "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}

# Keys that are present but obviously not real credentials
_PLACEHOLDER_KEYS: frozenset[str] = frozenset(
    {
        "your-api-key-here",
        "your_api_key_here",
        "sk-placeholder",
        "changeme",
        "replace_me",
        "todo",
        "xxx",
        "test",
        "<your-key>",
        "<api-key>",
    }
)


class StartupValidator:
    """Validates the runtime environment before the application starts serving.

    All checks are synchronous and make no network calls.  Instantiate once
    inside the FastAPI lifespan context manager and call ``validate()``.

    Returns
    -------
    list[str]
        A (possibly empty) list of human-readable error messages.
        Empty list means the environment is sane.
    """

    def validate(self) -> list[str]:
        errors: list[str] = []
        errors.extend(self._check_llm_key())
        errors.extend(self._check_workspace_dir())
        errors.extend(self._check_data_dir())
        errors.extend(self._check_jwt_secret())
        return errors

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_llm_key(self) -> list[str]:
        """Verify the configured LLM provider has a non-placeholder API key."""
        provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
        key_env = _PROVIDER_KEY_ENVS.get(provider)

        if key_env is None:
            # Provider (e.g. Ollama) does not need an API key
            return []

        key_value = os.getenv(key_env, "").strip()

        if not key_value:
            return [
                f"LLM provider '{provider}' requires {key_env} but it is not set. "
                f"Add {key_env}=<your-key> to .env or the environment."
            ]

        if key_value.lower() in _PLACEHOLDER_KEYS:
            return [
                f"{key_env} is set to a placeholder value '{key_value}'. "
                "Replace it with a real API key."
            ]

        return []

    def _check_workspace_dir(self) -> list[str]:
        """Verify that WORKSPACE_DIR exists and is writable."""
        return self._check_writable_dir(
            os.getenv("WORKSPACE_DIR", "temp-workspace"), "WORKSPACE_DIR"
        )

    def _check_data_dir(self) -> list[str]:
        """Verify that DATA_DIR exists and is writable."""
        return self._check_writable_dir(
            os.getenv("DATA_DIR", "data"), "DATA_DIR"
        )

    def _check_jwt_secret(self) -> list[str]:
        """When AUTH_ENABLED=true, verify JWT_SECRET_KEY is set and not default."""
        auth_enabled = os.getenv("AUTH_ENABLED", "false").lower() in ("true", "1", "yes")
        if not auth_enabled:
            return []

        secret = os.getenv("JWT_SECRET_KEY", "").strip()
        if not secret:
            return [
                "AUTH_ENABLED=true but JWT_SECRET_KEY is not set. "
                "Generate a secret with: python -c \"import secrets; print(secrets.token_hex(32))\""
            ]

        _WEAK_SECRETS = frozenset(
            {"secret", "changeme", "your-secret-key", "jwt-secret", "supersecret", "password"}
        )
        if secret.lower() in _WEAK_SECRETS or len(secret) < 16:
            return [
                "JWT_SECRET_KEY is too short or uses a known-weak default. "
                "Use a randomly generated secret of at least 32 characters."
            ]

        return []

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_writable_dir(dir_path: str, env_name: str) -> list[str]:
        """Attempt to create *dir_path* and verify a file can be written there."""
        path = Path(dir_path)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return [
                f"{env_name} directory '{dir_path}' could not be created: {exc}"
            ]

        probe = path / ".startup_probe"
        try:
            probe.write_text("ok")
            probe.unlink()
        except OSError as exc:
            return [
                f"{env_name} directory '{dir_path}' is not writable: {exc}"
            ]

        return []
