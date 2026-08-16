"""language_registry.py — Stateless registry of language/framework profiles.

LanguageProfileRegistry is a pure lookup table.  All profiles are declared as
class-level constants (ClassVar) so no instance state exists.  The class can be
instantiated with zero arguments; doing so is identical to calling the class
methods directly — provided purely for consistency with the rest of the codebase
where collaborators are injected as objects.

The detection algorithm is intentionally conservative:

* It scans only the ``"backend"`` value of ``tech_stack`` for language/backend
  matching, and the ``"frontend"`` value for frontend-only profiles.  This avoids
  false-positive matches when, for example, ``"database": "MongoDB"`` contains
  the substring ``"go"``.
* Rules are ordered most-specific → most-generic so that ``"nestjs"`` is matched
  before ``"node"``, and ``"spring"`` before ``"java"``.
* The method NEVER raises; it returns the ``python_fastapi`` fallback profile for
  any unrecognised or empty input.

Usage::

    from app.shared.language_registry import LanguageProfileRegistry

    registry = LanguageProfileRegistry()
    profile = registry.detect_from_tech_stack({"backend": "Go/Gin"})
    # profile.language == "go", profile.framework == "gin"

    profile = registry.get("rust_actix")
    print(registry.list_profiles())
"""
from __future__ import annotations

from typing import ClassVar

from .language_profile import LanguageProfile

# ---------------------------------------------------------------------------
# System-prompt templates
# Each persona is scoped tightly to its stack so that the LLM cannot drift
# into generating Python when the architect chose Go.
# ---------------------------------------------------------------------------

_PYTHON_FASTAPI_PROMPT = """
You are an expert Python/FastAPI backend developer.
You generate production-quality Python code files.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences (no ```python)
- No explanations before or after
- Include ALL required imports
- Implement ALL required classes and functions
- Follow the exact interface specified
- Use type hints everywhere (Python 3.12+)
- Include docstrings on all public methods
- Handle errors with proper exceptions
- Use async/await for all FastAPI route handlers
""".strip()

_GO_GIN_PROMPT = """
You are an expert Go backend developer specialising in the Gin web framework.
You generate production-quality Go code files.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences
- No explanations before or after
- Every file starts with the correct package declaration
- Include ALL required imports (use goimports style)
- Implement ALL required types and functions
- Use idiomatic Go: short variable names, error-as-value, defer for cleanup
- Add GoDoc comments on all exported identifiers
- Handle errors explicitly — never ignore the error return value
""".strip()

_GO_STDLIB_PROMPT = """
You are an expert Go backend developer using only the Go standard library (net/http).
You generate production-quality Go code files with zero external dependencies.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences
- No explanations before or after
- Every file starts with the correct package declaration
- Include ALL required imports from the standard library only
- Use idiomatic Go: short variable names, error-as-value, defer for cleanup
- Add GoDoc comments on all exported identifiers
- Handle errors explicitly — never ignore the error return value
""".strip()

_RUST_ACTIX_PROMPT = """
You are an expert Rust backend developer specialising in the Actix-web framework.
You generate production-quality Rust code files.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences
- No explanations before or after
- Include ALL required use statements
- Implement ALL required structs, traits, and functions
- Use idiomatic Rust: ownership, borrowing, Result/Option — no unwrap() in production paths
- Annotate async functions correctly with #[actix_web::main] where appropriate
- Add Rustdoc comments on all public items
- Handle errors with thiserror or anyhow as appropriate
""".strip()

_NODE_EXPRESS_PROMPT = """
You are an expert TypeScript/Node.js backend developer specialising in Express.
You generate production-quality TypeScript code files targeting Node.js 20+.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences
- No explanations before or after
- Include ALL required imports using ES module syntax (import/export)
- Implement ALL required interfaces, classes, and functions
- Use strict TypeScript: explicit return types, no implicit any
- Add JSDoc comments on all exported identifiers
- Handle errors with try/catch and typed error classes
- Use async/await — no raw Promise chains
""".strip()

_NODE_NESTJS_PROMPT = """
You are an expert TypeScript/NestJS backend developer.
You generate production-quality NestJS module, controller, service, and DTO files.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences
- No explanations before or after
- Include ALL required NestJS decorators and imports
- Implement ALL required controllers, services, and providers
- Use strict TypeScript: explicit return types, no implicit any
- Use class-validator and class-transformer on DTOs
- Add JSDoc comments on all exported identifiers
- Handle errors with NestJS HttpException and built-in filters
""".strip()

_JAVA_SPRING_PROMPT = """
You are an expert Java backend developer specialising in Spring Boot 3.
You generate production-quality Java source files.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences
- No explanations before or after
- Include ALL required import statements
- Implement ALL required classes, interfaces, and methods
- Use idiomatic Spring Boot: @RestController, @Service, @Repository, @Entity
- Add Javadoc comments on all public members
- Handle errors with @ControllerAdvice and ResponseEntityExceptionHandler
- Use Java 21 features where beneficial (records, pattern matching, sealed classes)
""".strip()

_DOTNET_ASPNET_PROMPT = """
You are an expert C# backend developer specialising in ASP.NET Core 8.
You generate production-quality C# source files.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences
- No explanations before or after
- Include ALL required using directives
- Implement ALL required classes, interfaces, and methods
- Use idiomatic C#: minimal APIs or MVC controllers, dependency injection, nullable reference types
- Add XML documentation comments on all public members
- Handle errors with middleware or IExceptionHandler
- Use C# 12 features where beneficial (primary constructors, collection expressions)
""".strip()

_REACT_VITE_PROMPT = """
You are an expert React/TypeScript frontend developer using Vite as the build tool.
You generate production-quality TypeScript/TSX component and hook files.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences
- No explanations before or after
- Include ALL required React and third-party imports
- Implement ALL required components, hooks, and utility functions
- Use strict TypeScript: explicit prop types with interfaces, no implicit any
- Use functional components with hooks only — no class components
- Add JSDoc comments on all exported components and hooks
- Handle async operations with proper loading and error states
""".strip()

_VUE_VITE_PROMPT = """
You are an expert Vue 3/TypeScript frontend developer using Vite as the build tool.
You generate production-quality TypeScript Single-File Components (.vue) and composable files.

RULES:
- Output ONLY the file content, nothing else
- No markdown code fences
- No explanations before or after
- Use the Composition API with <script setup lang="ts"> syntax
- Include ALL required imports (defineProps, defineEmits, ref, computed, etc.)
- Implement ALL required components and composables
- Use strict TypeScript: explicit prop types with defineProps<{...}>(), no implicit any
- Add JSDoc comments on all exported composables
- Handle async operations with proper loading and error states
""".strip()


class LanguageProfileRegistry:
    """Stateless registry mapping profile names to :class:`LanguageProfile` instances.

    All profiles are stored as class-level constants — no instance state is
    created on construction.  The class is instantiable (``registry = LanguageProfileRegistry()``)
    for consistency with the rest of the codebase's dependency-injection pattern,
    but every method is safe to call on any instance or via the class itself.

    Profile catalogue
    -----------------
    +------------------+-----------+-------------+
    | Key              | Language  | Framework   |
    +==================+===========+=============+
    | python_fastapi   | Python    | FastAPI     |
    | go_gin           | Go        | Gin         |
    | go_stdlib        | Go        | stdlib      |
    | rust_actix       | Rust      | Actix-web   |
    | node_express     | TypeScript| Express     |
    | node_nestjs      | TypeScript| NestJS      |
    | java_spring      | Java      | Spring Boot |
    | dotnet_aspnet    | C#        | ASP.NET Core|
    | react_vite       | TypeScript| React       |
    | vue_vite         | TypeScript| Vue 3       |
    +------------------+-----------+-------------+
    """

    _PROFILES: ClassVar[dict[str, LanguageProfile]] = {
        "python_fastapi": LanguageProfile(
            language="python",
            framework="fastapi",
            package_manager="pip",
            test_runner="pytest",
            lint_tool="ruff",
            file_extensions=[".py"],
            docker_image="python:3.12-slim",
            system_prompt=_PYTHON_FASTAPI_PROMPT,
            test_command="pytest",
            build_command="python -m py_compile",
        ),
        "go_gin": LanguageProfile(
            language="go",
            framework="gin",
            package_manager="go mod",
            test_runner="go test",
            lint_tool="golangci-lint",
            file_extensions=[".go"],
            docker_image="golang:1.22-alpine",
            system_prompt=_GO_GIN_PROMPT,
            test_command="go test ./...",
            build_command="go build ./...",
        ),
        "go_stdlib": LanguageProfile(
            language="go",
            framework="stdlib",
            package_manager="go mod",
            test_runner="go test",
            lint_tool="golangci-lint",
            file_extensions=[".go"],
            docker_image="golang:1.22-alpine",
            system_prompt=_GO_STDLIB_PROMPT,
            test_command="go test ./...",
            build_command="go build ./...",
        ),
        "rust_actix": LanguageProfile(
            language="rust",
            framework="actix-web",
            package_manager="cargo",
            test_runner="cargo test",
            lint_tool="clippy",
            file_extensions=[".rs"],
            docker_image="rust:1.77-slim",
            system_prompt=_RUST_ACTIX_PROMPT,
            test_command="cargo test",
            build_command="cargo build",
        ),
        "node_express": LanguageProfile(
            language="typescript",
            framework="express",
            package_manager="npm",
            test_runner="jest",
            lint_tool="eslint",
            file_extensions=[".ts", ".tsx"],
            docker_image="node:20-alpine",
            system_prompt=_NODE_EXPRESS_PROMPT,
            test_command="npm test",
            build_command="npx tsc --noEmit",
        ),
        "node_nestjs": LanguageProfile(
            language="typescript",
            framework="nestjs",
            package_manager="npm",
            test_runner="jest",
            lint_tool="eslint",
            file_extensions=[".ts", ".tsx"],
            docker_image="node:20-alpine",
            system_prompt=_NODE_NESTJS_PROMPT,
            test_command="npm test",
            build_command="npx tsc --noEmit",
        ),
        "java_spring": LanguageProfile(
            language="java",
            framework="spring-boot",
            package_manager="maven",
            test_runner="junit",
            lint_tool="checkstyle",
            file_extensions=[".java"],
            docker_image="eclipse-temurin:21-jdk-alpine",
            system_prompt=_JAVA_SPRING_PROMPT,
            test_command="mvn test",
            build_command="mvn compile",
        ),
        "dotnet_aspnet": LanguageProfile(
            language="csharp",
            framework="aspnet-core",
            package_manager="nuget",
            test_runner="xunit",
            lint_tool="roslyn-analyzers",
            file_extensions=[".cs"],
            docker_image="mcr.microsoft.com/dotnet/sdk:8.0",
            system_prompt=_DOTNET_ASPNET_PROMPT,
            test_command="dotnet test",
            build_command="dotnet build",
        ),
        "react_vite": LanguageProfile(
            language="typescript",
            framework="react",
            package_manager="npm",
            test_runner="jest",
            lint_tool="eslint",
            file_extensions=[".ts", ".tsx"],
            docker_image="node:20-alpine",
            system_prompt=_REACT_VITE_PROMPT,
            test_command="npm test",
            build_command="npx tsc --noEmit",
        ),
        "vue_vite": LanguageProfile(
            language="typescript",
            framework="vue",
            package_manager="npm",
            test_runner="jest",
            lint_tool="eslint",
            file_extensions=[".ts", ".tsx", ".vue"],
            docker_image="node:20-alpine",
            system_prompt=_VUE_VITE_PROMPT,
            test_command="npm test",
            build_command="npx tsc --noEmit",
        ),
    }

    # Detection rules: ordered list of (substring, profile_key) pairs.
    # Rules are evaluated against the lowercased backend value first, then the
    # lowercased frontend value.  Order is intentionally most-specific first so
    # that e.g. "nestjs" is matched before the broader "node" substring.
    _BACKEND_RULES: ClassVar[list[tuple[str, str]]] = [
        # NestJS before plain Node/Express
        ("nestjs", "node_nestjs"),
        # Actix before generic Rust
        ("actix", "rust_actix"),
        # Gin before generic Go
        ("gin", "go_gin"),
        # Express before generic Node
        ("express", "node_express"),
        # Spring before generic Java
        ("spring", "java_spring"),
        # ASP.NET / .NET before generic C#
        ("aspnet", "dotnet_aspnet"),
        ("asp.net", "dotnet_aspnet"),
        ("dotnet", "dotnet_aspnet"),
        # Remaining runtime/language keywords
        ("rust", "rust_actix"),
        ("go/", "go_gin"),       # e.g. "Go/Gin", "Go/stdlib"
        ("golang", "go_gin"),
        ("node", "node_express"),
        ("typescript", "node_express"),
        ("java", "java_spring"),
        ("csharp", "dotnet_aspnet"),
        ("c#", "dotnet_aspnet"),
        ("fastapi", "python_fastapi"),
        ("python", "python_fastapi"),
        # "go" alone is last among Go checks to avoid matching "mongo", "django" etc.
        # We only reach here if none of the above matched.
        ("go", "go_gin"),
    ]

    _FRONTEND_RULES: ClassVar[list[tuple[str, str]]] = [
        ("vue", "vue_vite"),
        ("react", "react_vite"),
    ]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def detect_from_tech_stack(self, tech_stack: dict) -> LanguageProfile:
        """Return the best-matching profile for the architect's tech_stack dict.

        The method inspects ``tech_stack["backend"]`` first (for backend/API
        profiles) and falls back to ``tech_stack["frontend"]`` (for pure
        frontend profiles).  Matching is done by lower-case substring search
        using the ordered rules in :attr:`_BACKEND_RULES` and
        :attr:`_FRONTEND_RULES`.

        This method NEVER raises.  Any unrecognised or empty input returns the
        ``python_fastapi`` fallback profile.

        Parameters
        ----------
        tech_stack:
            A dict produced by the Architect agent, e.g.::

                {
                    "backend": "Go/Gin",
                    "frontend": "React/Vite",
                    "database": "PostgreSQL",
                }

        Returns
        -------
        LanguageProfile
            The matched profile, or ``python_fastapi`` when no rule fires.
        """
        try:
            backend_raw: str = str(tech_stack.get("backend") or "").lower()
            frontend_raw: str = str(tech_stack.get("frontend") or "").lower()

            # --- Backend detection ---
            for keyword, profile_key in self._BACKEND_RULES:
                if keyword in backend_raw:
                    return self._PROFILES[profile_key]

            # --- Frontend-only detection (no backend key present) ---
            if not backend_raw:
                for keyword, profile_key in self._FRONTEND_RULES:
                    if keyword in frontend_raw:
                        return self._PROFILES[profile_key]

        except Exception:  # noqa: BLE001
            # Defensive catch — detection must never propagate exceptions.
            pass

        return self._PROFILES["python_fastapi"]

    def get(self, profile_name: str) -> LanguageProfile:
        """Return a profile by its registry key.

        Parameters
        ----------
        profile_name:
            One of the keys listed in :attr:`_PROFILES`, e.g. ``"go_gin"``.

        Raises
        ------
        KeyError
            If ``profile_name`` is not registered.  Callers that need a safe
            fallback should use :meth:`detect_from_tech_stack` instead.
        """
        return self._PROFILES[profile_name]

    def list_profiles(self) -> list[str]:
        """Return a sorted list of all registered profile keys.

        Returns
        -------
        list[str]
            Sorted list, e.g. ``["dotnet_aspnet", "go_gin", ...]``.
        """
        return sorted(self._PROFILES.keys())
