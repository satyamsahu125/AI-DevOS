"""test_dynamic_prompts.py — Tests for dynamic language profile wiring in agents.

Verifies that BackendDeveloperAgent and FrontendDeveloperAgent:
  - Return a profile-specific system prompt (not a hardcoded Python/React string)
  - Detect the correct profile from a context dict containing tech_stack
  - Fall back gracefully when context is missing, None, or unrecognised

Covers all three spec-required tests plus additional edge-case coverage.

Running::

    cd backend
    python -m pytest tests/test_dynamic_prompts.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.shared.language_profile import LanguageProfile
from app.shared.language_registry import LanguageProfileRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_backend_agent(language_profile: LanguageProfile | None = None):
    """Construct a BackendDeveloperAgent with all heavy deps mocked out."""
    # Import here so module-level errors don't block collection
    from app.agents.backend import BackendDeveloperAgent

    mock_llm = MagicMock()
    mock_writer = MagicMock()
    mock_validator = MagicMock()

    return BackendDeveloperAgent(
        llm_manager=mock_llm,
        project_writer=mock_writer,
        validator=mock_validator,
        language_profile=language_profile,
    )


def _make_frontend_agent(language_profile: LanguageProfile | None = None):
    """Construct a FrontendDeveloperAgent with all heavy deps mocked out."""
    from app.agents.frontend import FrontendDeveloperAgent

    mock_llm = MagicMock()
    mock_writer = MagicMock()
    mock_validator = MagicMock()

    return FrontendDeveloperAgent(
        llm_manager=mock_llm,
        project_writer=mock_writer,
        validator=mock_validator,
        language_profile=language_profile,
    )


# ---------------------------------------------------------------------------
# Spec-required tests
# ---------------------------------------------------------------------------

class TestBackendAgentSystemPrompt:
    """Spec test 1: _file_system_prompt returns profile.system_prompt."""

    def test_backend_agent_uses_go_profile(self) -> None:
        """With go_gin profile injected, system prompt must mention Go, not Python."""
        registry = LanguageProfileRegistry()
        go_profile = registry.get("go_gin")
        agent = _make_backend_agent(language_profile=go_profile)

        result = agent._file_system_prompt(go_profile)

        assert "Go" in result, "Expected 'Go' in system prompt for go_gin profile"
        assert "Python" not in result, "Expected no 'Python' in system prompt for go_gin profile"

    def test_backend_agent_uses_rust_profile(self) -> None:
        """With rust_actix profile injected, system prompt must mention Rust."""
        registry = LanguageProfileRegistry()
        rust_profile = registry.get("rust_actix")
        agent = _make_backend_agent(language_profile=rust_profile)

        result = agent._file_system_prompt(rust_profile)

        assert "Rust" in result
        assert "Python" not in result

    def test_backend_agent_uses_java_profile(self) -> None:
        """With java_spring profile injected, system prompt must mention Java."""
        registry = LanguageProfileRegistry()
        java_profile = registry.get("java_spring")
        agent = _make_backend_agent(language_profile=java_profile)

        result = agent._file_system_prompt(java_profile)

        assert "Java" in result or "Spring" in result
        assert "Python" not in result

    def test_backend_agent_python_profile_mentions_python(self) -> None:
        """Python/FastAPI profile system prompt must mention Python."""
        registry = LanguageProfileRegistry()
        py_profile = registry.get("python_fastapi")
        agent = _make_backend_agent(language_profile=py_profile)

        result = agent._file_system_prompt(py_profile)

        assert "Python" in result or "FastAPI" in result


class TestBackendAgentProfileDetection:
    """Spec test 2: _resolve_language_profile extracts language from context."""

    def test_backend_agent_detects_from_context(self) -> None:
        """Context with tech_stack={'backend': 'Go/Gin'} → go profile."""
        agent = _make_backend_agent()
        context = {"tech_stack": {"backend": "Go/Gin"}}

        profile = agent._resolve_language_profile(context)

        assert profile.language == "go", f"Expected language='go', got {profile.language!r}"

    def test_backend_agent_detects_python_from_context(self) -> None:
        """Context with Python/FastAPI backend → python_fastapi profile."""
        agent = _make_backend_agent()
        context = {"tech_stack": {"backend": "Python/FastAPI"}}

        profile = agent._resolve_language_profile(context)

        assert profile.language == "python"
        assert profile.framework == "fastapi"

    def test_backend_agent_detects_rust_from_context(self) -> None:
        """Context with Rust/Actix backend → rust_actix profile."""
        agent = _make_backend_agent()
        context = {"tech_stack": {"backend": "Rust/Actix"}}

        profile = agent._resolve_language_profile(context)

        assert profile.language == "rust"

    def test_backend_agent_explicit_profile_wins_over_context(self) -> None:
        """Explicitly injected profile takes precedence over conflicting context."""
        registry = LanguageProfileRegistry()
        go_profile = registry.get("go_gin")
        agent = _make_backend_agent(language_profile=go_profile)

        # Context says Python — explicit Go profile must win
        context = {"tech_stack": {"backend": "Python/FastAPI"}}
        profile = agent._resolve_language_profile(context)

        assert profile.language == "go", "Explicit injection must win over context"

    def test_backend_agent_fallback_on_unknown_context(self) -> None:
        """Unrecognised tech_stack falls back to python_fastapi."""
        agent = _make_backend_agent()
        context = {"tech_stack": {"backend": "COBOL/Enterprise"}}

        profile = agent._resolve_language_profile(context)

        assert profile.language == "python"
        assert profile.framework == "fastapi"

    def test_backend_agent_fallback_on_empty_context(self) -> None:
        """Empty context dict falls back to python_fastapi."""
        agent = _make_backend_agent()

        profile = agent._resolve_language_profile({})

        assert profile.language == "python"

    def test_backend_agent_fallback_on_none_context(self) -> None:
        """None context falls back to python_fastapi without raising."""
        agent = _make_backend_agent()

        profile = agent._resolve_language_profile(None)

        assert profile.language == "python"

    def test_backend_agent_caches_resolved_profile(self) -> None:
        """After resolution, _resolved_profile is set for observability."""
        agent = _make_backend_agent()
        context = {"tech_stack": {"backend": "Go/Gin"}}

        assert agent._resolved_profile is None, "Should start unset"
        agent._resolve_language_profile(context)
        assert agent._resolved_profile is not None
        assert agent._resolved_profile.language == "go"

    def test_backend_agent_detects_from_json_string_context(self) -> None:
        """JSON string context is parsed correctly."""
        import json
        agent = _make_backend_agent()
        context = json.dumps({"tech_stack": {"backend": "Rust/Actix"}})

        profile = agent._resolve_language_profile(context)

        assert profile.language == "rust"

    def test_backend_agent_detects_from_nested_architect_key(self) -> None:
        """tech_stack nested under 'architect' key is extracted."""
        agent = _make_backend_agent()
        context = {"architect": {"tech_stack": {"backend": "Go/Gin"}}}

        profile = agent._resolve_language_profile(context)

        assert profile.language == "go"

    def test_backend_agent_detects_from_stage_artifact(self) -> None:
        """StageArtifact-like object with .content attribute is supported."""
        import json
        agent = _make_backend_agent()

        fake_artifact = MagicMock()
        fake_artifact.content = json.dumps({"tech_stack": {"backend": "Node.js/Express"}})

        profile = agent._resolve_language_profile(fake_artifact)

        assert profile.language == "typescript"
        assert profile.framework == "express"


class TestFrontendAgentProfileDetection:
    """Spec test 3: FrontendDeveloperAgent detects Vue from context."""

    def test_frontend_agent_detects_vue(self) -> None:
        """Context with tech_stack={'frontend': 'Vue/Vite'} → vue_vite profile."""
        agent = _make_frontend_agent()
        context = {"tech_stack": {"frontend": "Vue/Vite"}}

        profile = agent._resolve_language_profile(context)

        assert profile.framework == "vue", f"Expected framework='vue', got {profile.framework!r}"

    def test_frontend_agent_detects_react(self) -> None:
        """Context with React/Vite frontend → react_vite profile."""
        agent = _make_frontend_agent()
        context = {"tech_stack": {"frontend": "React/Vite"}}

        profile = agent._resolve_language_profile(context)

        assert profile.framework == "react"

    def test_frontend_agent_ignores_backend_key(self) -> None:
        """Frontend agent must NOT use the backend language for its profile."""
        agent = _make_frontend_agent()
        # Full-stack project: Go backend, React frontend
        context = {"tech_stack": {"backend": "Go/Gin", "frontend": "React/Vite"}}

        profile = agent._resolve_language_profile(context)

        # Must be a frontend profile, not go_gin
        assert profile.framework == "react", (
            f"Frontend agent must detect React, not Go. Got framework={profile.framework!r}"
        )

    def test_frontend_agent_default_fallback_is_react_vite(self) -> None:
        """Unrecognised frontend tech defaults to react_vite, not python_fastapi."""
        agent = _make_frontend_agent()
        context = {"tech_stack": {"frontend": "UnknownFramework/Beta"}}

        profile = agent._resolve_language_profile(context)

        assert profile.framework == "react", (
            f"Frontend fallback must be react_vite, got {profile.framework!r}"
        )
        assert profile.language == "typescript"

    def test_frontend_agent_fallback_on_empty_context(self) -> None:
        """Empty context → react_vite fallback, not python."""
        agent = _make_frontend_agent()

        profile = agent._resolve_language_profile({})

        assert profile.framework == "react"
        assert profile.language == "typescript"

    def test_frontend_agent_explicit_profile_wins(self) -> None:
        """Explicitly injected profile wins over context."""
        registry = LanguageProfileRegistry()
        vue_profile = registry.get("vue_vite")
        agent = _make_frontend_agent(language_profile=vue_profile)

        # Context says React — injected Vue must win
        context = {"tech_stack": {"frontend": "React/Vite"}}
        profile = agent._resolve_language_profile(context)

        assert profile.framework == "vue"

    def test_frontend_agent_system_prompt_uses_profile(self) -> None:
        """_file_system_prompt returns profile.system_prompt for frontend profiles."""
        registry = LanguageProfileRegistry()
        vue_profile = registry.get("vue_vite")
        agent = _make_frontend_agent(language_profile=vue_profile)

        result = agent._file_system_prompt(vue_profile)

        assert "Vue" in result, "Expected 'Vue' in system prompt for vue_vite profile"
        assert "React" not in result or "React Native" not in result, (
            "vue_vite prompt should not contain React/TypeScript React framing"
        )

    def test_frontend_agent_caches_resolved_profile(self) -> None:
        """After resolution, _resolved_profile is set for observability."""
        agent = _make_frontend_agent()
        context = {"tech_stack": {"frontend": "Vue/Vite"}}

        assert agent._resolved_profile is None
        agent._resolve_language_profile(context)
        assert agent._resolved_profile is not None
        assert agent._resolved_profile.framework == "vue"


class TestBackendPromptBuilderProfile:
    """Tests for BackendPromptBuilder.build() with language_profile parameter."""

    def test_builder_build_without_profile_is_unchanged(self) -> None:
        """Calling build() without language_profile behaves identically to before."""
        from app.prompt.backend_builder import BackendPromptBuilder
        builder = BackendPromptBuilder()

        result = builder.build(context=None, language_profile=None)

        assert "Backend Prompt" in result
        # No profile hint block should appear
        assert "RESOLVED TECHNOLOGY PROFILE" not in result

    def test_builder_build_with_profile_injects_hint(self) -> None:
        """Calling build() with a profile injects the technology hint block."""
        from app.prompt.backend_builder import BackendPromptBuilder, SYSTEM_PROMPT
        registry = LanguageProfileRegistry()
        go_profile = registry.get("go_gin")
        builder = BackendPromptBuilder()

        result = builder.build(context=None, language_profile=go_profile)

        assert "RESOLVED TECHNOLOGY PROFILE" in result
        assert "go" in result
        assert "gin" in result
        assert "go mod" in result

    def test_builder_build_profile_hint_includes_all_fields(self) -> None:
        """The profile hint block contains all required technology fields."""
        from app.prompt.backend_builder import BackendPromptBuilder
        registry = LanguageProfileRegistry()
        rust_profile = registry.get("rust_actix")
        builder = BackendPromptBuilder()

        result = builder.build(context=None, language_profile=rust_profile)

        assert "rust" in result
        assert "actix-web" in result
        assert "cargo" in result
        assert "clippy" in result
        assert ".rs" in result

    def test_builder_backward_compat_positional_context(self) -> None:
        """build(context) with no language_profile keyword must still work."""
        from app.prompt.backend_builder import BackendPromptBuilder
        builder = BackendPromptBuilder()

        # Should not raise — backward compat
        result = builder.build(None)
        assert result  # non-empty
