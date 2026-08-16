"""test_language_registry.py — Unit tests for LanguageProfileRegistry.

Covers:
  - detect_from_tech_stack: all required detection cases
  - detect_from_tech_stack: fallback to python_fastapi on unknown input
  - get: returns the correct LanguageProfile by key
  - get: raises KeyError for unknown key
  - list_profiles: returns a sorted list of all registered keys
  - LanguageProfile: frozen (immutable) dataclass behaviour
  - LanguageProfile: all required fields are accessible

Running::

    cd backend
    python -m pytest tests/test_language_registry.py -v
"""
from __future__ import annotations

import pytest

from app.shared.language_profile import LanguageProfile
from app.shared.language_registry import LanguageProfileRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def registry() -> LanguageProfileRegistry:
    """Return a fresh LanguageProfileRegistry for each test."""
    return LanguageProfileRegistry()


# ---------------------------------------------------------------------------
# Detection tests — required by specification
# ---------------------------------------------------------------------------

class TestDetectFromTechStack:
    """Tests for LanguageProfileRegistry.detect_from_tech_stack."""

    def test_detect_python_fastapi(self, registry: LanguageProfileRegistry) -> None:
        """Python/FastAPI backend resolves to the python_fastapi profile."""
        tech_stack = {"backend": "Python/FastAPI"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.language == "python"
        assert profile.framework == "fastapi"

    def test_detect_go_gin(self, registry: LanguageProfileRegistry) -> None:
        """Go/Gin backend resolves to the go_gin profile."""
        tech_stack = {"backend": "Go/Gin"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.language == "go"
        assert profile.framework == "gin"

    def test_detect_rust(self, registry: LanguageProfileRegistry) -> None:
        """Rust/Actix backend resolves to the rust_actix profile."""
        tech_stack = {"backend": "Rust/Actix"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.language == "rust"
        assert profile.framework == "actix-web"

    def test_detect_node(self, registry: LanguageProfileRegistry) -> None:
        """Node.js/Express backend resolves to the node_express profile."""
        tech_stack = {"backend": "Node.js/Express"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.language == "typescript"
        assert profile.framework == "express"

    def test_fallback_to_python(self, registry: LanguageProfileRegistry) -> None:
        """Unrecognised backend value falls back to python_fastapi."""
        tech_stack = {"backend": "unknown_framework"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.language == "python"
        assert profile.framework == "fastapi"


# ---------------------------------------------------------------------------
# Additional detection coverage
# ---------------------------------------------------------------------------

class TestDetectAdditionalProfiles:
    """Extended detection tests beyond the minimum required by specification."""

    def test_detect_nestjs(self, registry: LanguageProfileRegistry) -> None:
        """NestJS backend resolves to node_nestjs, not node_express."""
        tech_stack = {"backend": "Node.js/NestJS"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.framework == "nestjs"

    def test_detect_java_spring(self, registry: LanguageProfileRegistry) -> None:
        """Spring Boot backend resolves to java_spring."""
        tech_stack = {"backend": "Java/Spring Boot"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.language == "java"
        assert profile.framework == "spring-boot"

    def test_detect_dotnet_aspnet(self, registry: LanguageProfileRegistry) -> None:
        """ASP.NET Core backend resolves to dotnet_aspnet."""
        tech_stack = {"backend": "C#/ASP.NET Core"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.language == "csharp"
        assert profile.framework == "aspnet-core"

    def test_detect_react_frontend_only(self, registry: LanguageProfileRegistry) -> None:
        """React in frontend with no backend resolves to react_vite."""
        tech_stack = {"frontend": "React/Vite"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.framework == "react"

    def test_detect_vue_frontend_only(self, registry: LanguageProfileRegistry) -> None:
        """Vue in frontend with no backend resolves to vue_vite."""
        tech_stack = {"frontend": "Vue/Vite"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.framework == "vue"

    def test_nestjs_wins_over_express(self, registry: LanguageProfileRegistry) -> None:
        """NestJS takes priority over the broader 'node' substring."""
        tech_stack = {"backend": "NestJS/TypeScript"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.framework == "nestjs"

    def test_actix_wins_over_generic_rust(self, registry: LanguageProfileRegistry) -> None:
        """Actix-specific keyword still resolves correctly."""
        tech_stack = {"backend": "Rust/Actix-web"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.framework == "actix-web"

    def test_full_stack_backend_detection(self, registry: LanguageProfileRegistry) -> None:
        """Backend key takes precedence when both frontend and backend are present."""
        tech_stack = {
            "backend": "Go/Gin",
            "frontend": "React/Vite",
            "database": "PostgreSQL",
        }
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.language == "go"
        assert profile.framework == "gin"

    def test_empty_dict_falls_back_to_python(self, registry: LanguageProfileRegistry) -> None:
        """Empty tech_stack always returns python_fastapi fallback."""
        profile = registry.detect_from_tech_stack({})
        assert profile.language == "python"
        assert profile.framework == "fastapi"

    def test_none_values_do_not_raise(self, registry: LanguageProfileRegistry) -> None:
        """None values in tech_stack are handled gracefully — no exception."""
        profile = registry.detect_from_tech_stack({"backend": None, "frontend": None})
        assert profile.language == "python"

    def test_non_string_values_do_not_raise(self, registry: LanguageProfileRegistry) -> None:
        """Non-string tech_stack values are coerced, not raised."""
        profile = registry.detect_from_tech_stack({"backend": 42})
        assert profile.language == "python"

    def test_database_mongo_does_not_match_go(self, registry: LanguageProfileRegistry) -> None:
        """'MongoDB' in the database key must NOT produce a Go profile."""
        tech_stack = {"backend": "Python/FastAPI", "database": "MongoDB"}
        profile = registry.detect_from_tech_stack(tech_stack)
        assert profile.language == "python"


# ---------------------------------------------------------------------------
# Registry API tests
# ---------------------------------------------------------------------------

class TestRegistryGet:
    """Tests for LanguageProfileRegistry.get."""

    def test_get_known_profile(self, registry: LanguageProfileRegistry) -> None:
        """get() returns a LanguageProfile for a valid key."""
        profile = registry.get("python_fastapi")
        assert isinstance(profile, LanguageProfile)
        assert profile.language == "python"

    def test_get_all_registered_profiles(self, registry: LanguageProfileRegistry) -> None:
        """Every key returned by list_profiles() is retrievable via get()."""
        for key in registry.list_profiles():
            profile = registry.get(key)
            assert isinstance(profile, LanguageProfile), f"get({key!r}) returned non-LanguageProfile"

    def test_get_unknown_profile_raises_key_error(self, registry: LanguageProfileRegistry) -> None:
        """get() raises KeyError for an unregistered profile name."""
        with pytest.raises(KeyError):
            registry.get("nonexistent_profile")


class TestRegistryListProfiles:
    """Tests for LanguageProfileRegistry.list_profiles."""

    _REQUIRED_KEYS = {
        "python_fastapi",
        "go_gin",
        "go_stdlib",
        "rust_actix",
        "node_express",
        "node_nestjs",
        "java_spring",
        "dotnet_aspnet",
        "react_vite",
        "vue_vite",
    }

    def test_list_profiles_returns_list(self, registry: LanguageProfileRegistry) -> None:
        """list_profiles() returns a list."""
        result = registry.list_profiles()
        assert isinstance(result, list)

    def test_list_profiles_contains_all_required(self, registry: LanguageProfileRegistry) -> None:
        """All ten required profiles are present."""
        result = set(registry.list_profiles())
        assert self._REQUIRED_KEYS.issubset(result), (
            f"Missing profiles: {self._REQUIRED_KEYS - result}"
        )

    def test_list_profiles_is_sorted(self, registry: LanguageProfileRegistry) -> None:
        """list_profiles() returns keys in sorted order."""
        result = registry.list_profiles()
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# LanguageProfile immutability tests
# ---------------------------------------------------------------------------

class TestLanguageProfileImmutability:
    """Tests that LanguageProfile behaves as a frozen (immutable) dataclass."""

    def test_profile_is_frozen(self, registry: LanguageProfileRegistry) -> None:
        """Assigning to any field on a LanguageProfile raises FrozenInstanceError."""
        profile = registry.get("python_fastapi")
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError is a subclass of AttributeError
            profile.language = "go"  # type: ignore[misc]

    def test_profile_is_not_hashable_due_to_list_field(self, registry: LanguageProfileRegistry) -> None:
        """Profiles contain a list[str] field (file_extensions) which prevents hashing.

        frozen=True prevents field *reassignment*; it does not guarantee hashability
        when a field is a mutable container.  This test documents the known Python
        invariant: a frozen dataclass that holds a list raises TypeError on hash().
        """
        profile = registry.get("go_gin")
        with pytest.raises(TypeError, match="unhashable type"):
            hash(profile)

    def test_profile_equality(self, registry: LanguageProfileRegistry) -> None:
        """Two lookups of the same key return equal objects."""
        p1 = registry.get("rust_actix")
        p2 = registry.get("rust_actix")
        assert p1 == p2


# ---------------------------------------------------------------------------
# LanguageProfile field coverage tests
# ---------------------------------------------------------------------------

class TestLanguageProfileFields:
    """Verify all required fields are present and non-empty on every profile."""

    _REQUIRED_FIELDS = [
        "language",
        "framework",
        "package_manager",
        "test_runner",
        "lint_tool",
        "file_extensions",
        "docker_image",
        "system_prompt",
        "test_command",
        "build_command",
    ]

    def test_all_profiles_have_required_fields(self, registry: LanguageProfileRegistry) -> None:
        """Every registered profile has all ten required fields with non-empty values."""
        for key in registry.list_profiles():
            profile = registry.get(key)
            for field_name in self._REQUIRED_FIELDS:
                value = getattr(profile, field_name)
                assert value, (
                    f"Profile {key!r} has empty or falsy field {field_name!r}: {value!r}"
                )

    def test_file_extensions_are_lists(self, registry: LanguageProfileRegistry) -> None:
        """file_extensions must be a list on every profile."""
        for key in registry.list_profiles():
            profile = registry.get(key)
            assert isinstance(profile.file_extensions, list), (
                f"Profile {key!r}: file_extensions is {type(profile.file_extensions)}, expected list"
            )

    def test_system_prompts_are_non_trivial(self, registry: LanguageProfileRegistry) -> None:
        """Each system_prompt is long enough to constitute a real expert persona (>50 chars)."""
        for key in registry.list_profiles():
            profile = registry.get(key)
            assert len(profile.system_prompt) > 50, (
                f"Profile {key!r}: system_prompt is suspiciously short: {profile.system_prompt!r}"
            )
