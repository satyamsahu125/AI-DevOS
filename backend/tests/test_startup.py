"""Tests for StartupValidator pre-flight checks.

Validates that the validator:
  1. Reports errors when the configured LLM provider has no API key.
  2. Passes cleanly when all required env vars are set and dirs are writable.
"""

import os
import tempfile
from unittest.mock import patch

import pytest

from app.core.startup_validator import StartupValidator


# ---------------------------------------------------------------------------
# 1. Missing API key — validator must surface an error
# ---------------------------------------------------------------------------

def test_startup_validator_fails_empty_key(tmp_path):
    """Validator returns at least one error message mentioning the API key
    when LLM_PROVIDER=claude but CLAUDE_API_KEY is absent."""
    workspace = str(tmp_path / "workspace")
    data = str(tmp_path / "data")

    env_overrides = {
        "LLM_PROVIDER": "claude",
        "CLAUDE_API_KEY": "",          # deliberately empty
        "WORKSPACE_DIR": workspace,
        "DATA_DIR": data,
        "AUTH_ENABLED": "false",
    }

    with patch.dict(os.environ, env_overrides, clear=False):
        errors = StartupValidator().validate()

    assert errors, "Expected at least one validation error but got none"

    combined = " ".join(errors).lower()
    assert "claude_api_key" in combined or "api key" in combined or "api_key" in combined, (
        f"Error messages do not mention the missing API key: {errors}"
    )


# ---------------------------------------------------------------------------
# 2. Happy path — validator must return an empty list
# ---------------------------------------------------------------------------

def test_startup_validator_passes(tmp_path):
    """Validator returns no errors when a real-looking API key is set and
    the workspace/data directories can be created and written to."""
    workspace = str(tmp_path / "workspace")
    data = str(tmp_path / "data")

    # Use a key value that passes the placeholder filter (32 hex chars)
    fake_key = "a" * 32

    env_overrides = {
        "LLM_PROVIDER": "claude",
        "CLAUDE_API_KEY": fake_key,
        "WORKSPACE_DIR": workspace,
        "DATA_DIR": data,
        "AUTH_ENABLED": "false",
    }

    with patch.dict(os.environ, env_overrides, clear=False):
        errors = StartupValidator().validate()

    assert errors == [], f"Expected no validation errors but got: {errors}"
