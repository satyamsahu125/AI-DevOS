"""test_phase5_env_config.py — Phase 5 Task 6: .env additions for sandbox config.

Verifies:
  1. The four spec-mandated env var names exist as module-level constants in code_sandbox.
  2. SANDBOX_ENABLED=false is the default (module-level _SANDBOX_ENABLED is False when
     the env var is unset or "false").
  3. CodeSandbox constructor `enabled` param overrides the module-level default.
  4. CodeSandbox constructor `timeout_seconds` param overrides the module-level default.
  5. When disabled (enabled=False, require_execution not set), run() returns a
     SandboxResult where enabled=False and project_id is set.
  6. SandboxResult.disabled() classmethod produces the expected shape.
  7. The .env file exists at backend/.env and contains all four sandbox entries.
  8. The four entries in .env match the spec-documented values exactly.

Running:
    cd backend
    python -m pytest tests/test_phase5_env_config.py -v
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# 1-2: Module-level env var constants exist and default correctly
# ---------------------------------------------------------------------------

class TestModuleLevelConstants:

    def test_sandbox_enabled_constant_exists(self):
        """_SANDBOX_ENABLED module constant must exist in code_sandbox."""
        import app.execution.code_sandbox as m
        assert hasattr(m, "_SANDBOX_ENABLED"), "_SANDBOX_ENABLED not defined in code_sandbox"

    def test_sandbox_timeout_constant_exists(self):
        import app.execution.code_sandbox as m
        assert hasattr(m, "_SANDBOX_TIMEOUT"), "_SANDBOX_TIMEOUT not defined in code_sandbox"

    def test_docker_python_constant_exists(self):
        import app.execution.code_sandbox as m
        assert hasattr(m, "_DOCKER_PYTHON"), "_DOCKER_PYTHON not defined in code_sandbox"

    def test_docker_node_constant_exists(self):
        import app.execution.code_sandbox as m
        assert hasattr(m, "_DOCKER_NODE"), "_DOCKER_NODE not defined in code_sandbox"

    def test_sandbox_enabled_default_is_false(self):
        """Spec mandates SANDBOX_ENABLED=false as default. Module reads "false" → False."""
        import app.execution.code_sandbox as m
        # The module-level value must be False when SANDBOX_ENABLED is absent or "false".
        # We can't re-import, but we can check the module default value matches spec intent.
        # If the test env has SANDBOX_ENABLED unset, _SANDBOX_ENABLED is False.
        env_val = os.getenv("SANDBOX_ENABLED", "false")
        expected = env_val.lower() in ("true", "1", "yes")
        assert m._SANDBOX_ENABLED == expected

    def test_sandbox_timeout_default_is_sixty(self):
        """Spec mandates SANDBOX_TIMEOUT=60 as default."""
        import app.execution.code_sandbox as m
        expected = int(os.getenv("SANDBOX_TIMEOUT", "60"))
        assert m._SANDBOX_TIMEOUT == expected

    def test_docker_python_default_matches_spec(self):
        """Spec mandates SANDBOX_DOCKER_PYTHON=python:3.12-slim."""
        import app.execution.code_sandbox as m
        expected = os.getenv("SANDBOX_DOCKER_PYTHON", "python:3.12-slim")
        assert m._DOCKER_PYTHON == expected

    def test_docker_node_default_matches_spec(self):
        """Spec mandates SANDBOX_DOCKER_NODE=node:20-slim."""
        import app.execution.code_sandbox as m
        expected = os.getenv("SANDBOX_DOCKER_NODE", "node:20-slim")
        assert m._DOCKER_NODE == expected


# ---------------------------------------------------------------------------
# 3-4: Constructor overrides
# ---------------------------------------------------------------------------

class TestConstructorOverrides:

    def test_enabled_true_override(self):
        """Constructor enabled=True overrides module-level False."""
        from app.execution.code_sandbox import CodeSandbox
        sb = CodeSandbox(enabled=True)
        # _enabled should be True regardless of module-level default
        assert sb._enabled is True

    def test_enabled_false_override(self):
        """Constructor enabled=False overrides module-level (even if it were True)."""
        from app.execution.code_sandbox import CodeSandbox
        sb = CodeSandbox(enabled=False)
        assert sb._enabled is False

    def test_timeout_override(self):
        """Constructor timeout_seconds overrides module-level _SANDBOX_TIMEOUT."""
        from app.execution.code_sandbox import CodeSandbox
        sb = CodeSandbox(timeout_seconds=42)
        assert sb._timeout == 42

    def test_timeout_default_uses_module_constant(self):
        """Without override, _timeout equals the module-level _SANDBOX_TIMEOUT."""
        from app.execution.code_sandbox import CodeSandbox, _SANDBOX_TIMEOUT
        sb = CodeSandbox()
        assert sb._timeout == _SANDBOX_TIMEOUT

    def test_no_enabled_override_uses_module_constant(self):
        """Without override, _enabled equals the module-level _SANDBOX_ENABLED."""
        from app.execution.code_sandbox import CodeSandbox, _SANDBOX_ENABLED
        sb = CodeSandbox()
        assert sb._enabled == _SANDBOX_ENABLED


# ---------------------------------------------------------------------------
# 5-6: Disabled sandbox returns correctly shaped SandboxResult
# ---------------------------------------------------------------------------

class TestDisabledSandbox:

    def test_disabled_run_returns_sandbox_result(self):
        """When enabled=False and require_execution not set, run() returns disabled result."""
        from app.execution.code_sandbox import CodeSandbox
        sb = CodeSandbox(enabled=False)
        result = sb.run("proj-disabled", sprint=1)
        assert result is not None
        assert result.project_id == "proj-disabled"

    def test_disabled_run_result_has_enabled_false(self):
        """Disabled SandboxResult must have enabled=False."""
        from app.execution.code_sandbox import CodeSandbox
        sb = CodeSandbox(enabled=False)
        result = sb.run("proj-dis2", sprint=0)
        assert result.enabled is False

    def test_sandbox_result_disabled_classmethod(self):
        """SandboxResult.disabled() produces correct shape."""
        from app.shared.dto.sandbox_result import SandboxResult
        result = SandboxResult.disabled("proj-x", sprint=3)
        assert result.project_id == "proj-x"
        assert result.sprint == 3
        assert result.enabled is False

    def test_disabled_run_never_raises(self):
        """run() with enabled=False must never raise regardless of project state."""
        from app.execution.code_sandbox import CodeSandbox
        sb = CodeSandbox(enabled=False, workspace_manager=None)
        # No workspace_manager, no project files — must still not raise
        result = sb.run("nonexistent-proj", sprint=99)
        assert result is not None


# ---------------------------------------------------------------------------
# 7-8: .env file exists with correct content
# ---------------------------------------------------------------------------

class TestDotEnvFile:

    _ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

    def test_env_file_exists(self):
        """`backend/.env` must exist (Phase 5 spec: NEW .env additions)."""
        assert self._ENV_PATH.exists(), f".env not found at {self._ENV_PATH}"

    def _env_entries(self) -> dict[str, str]:
        """Parse the .env file into key=value pairs (skip comments and blanks)."""
        entries: dict[str, str] = {}
        for line in self._ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                entries[k.strip()] = v.strip()
        return entries

    def test_sandbox_enabled_entry_present(self):
        entries = self._env_entries()
        assert "SANDBOX_ENABLED" in entries, "SANDBOX_ENABLED missing from .env"

    def test_sandbox_enabled_value_is_false(self):
        """Spec mandates SANDBOX_ENABLED=false as the safe default."""
        entries = self._env_entries()
        assert entries.get("SANDBOX_ENABLED") == "false"

    def test_sandbox_timeout_entry_present(self):
        entries = self._env_entries()
        assert "SANDBOX_TIMEOUT" in entries

    def test_sandbox_timeout_value_is_sixty(self):
        entries = self._env_entries()
        assert entries.get("SANDBOX_TIMEOUT") == "60"

    def test_sandbox_docker_python_entry_present(self):
        entries = self._env_entries()
        assert "SANDBOX_DOCKER_PYTHON" in entries

    def test_sandbox_docker_python_value_matches_spec(self):
        entries = self._env_entries()
        assert entries.get("SANDBOX_DOCKER_PYTHON") == "python:3.12-slim"

    def test_sandbox_docker_node_entry_present(self):
        entries = self._env_entries()
        assert "SANDBOX_DOCKER_NODE" in entries

    def test_sandbox_docker_node_value_matches_spec(self):
        entries = self._env_entries()
        assert entries.get("SANDBOX_DOCKER_NODE") == "node:20-slim"
