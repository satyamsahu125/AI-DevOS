"""language_profile.py — Immutable descriptor for a language/framework combination.

A LanguageProfile captures every technology-specific constant an agent needs to
generate code, run tests, and build artifacts for a given stack.  By making this
a frozen dataclass all fields are validated at construction time and no agent can
accidentally mutate shared registry state.

Usage::

    from app.shared.language_profile import LanguageProfile

    profile = LanguageProfile(
        language="python",
        framework="fastapi",
        package_manager="pip",
        test_runner="pytest",
        lint_tool="ruff",
        file_extensions=[".py"],
        docker_image="python:3.12-slim",
        system_prompt="You are an expert Python/FastAPI backend developer...",
        test_command="pytest",
        build_command="python -m py_compile",
    )
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    """Immutable descriptor for a single language/framework combination.

    All fields are required at construction time.  The ``frozen=True`` flag
    makes instances hashable and prevents accidental mutation — registry
    singletons are safe to share across agents without copying.

    Attributes
    ----------
    language:
        Canonical lower-case language name, e.g. ``"python"``, ``"go"``,
        ``"rust"``, ``"typescript"``, ``"java"``, ``"csharp"``.
    framework:
        Primary web / application framework, e.g. ``"fastapi"``, ``"gin"``,
        ``"actix-web"``, ``"express"``, ``"nestjs"``, ``"spring-boot"``.
    package_manager:
        Tool used to manage dependencies, e.g. ``"pip"``, ``"go mod"``,
        ``"cargo"``, ``"npm"``, ``"maven"``, ``"nuget"``.
    test_runner:
        Command or tool used to run the test suite, e.g. ``"pytest"``,
        ``"go test"``, ``"cargo test"``, ``"jest"``, ``"junit"``.
    lint_tool:
        Static analysis / linting tool, e.g. ``"ruff"``, ``"golangci-lint"``,
        ``"clippy"``, ``"eslint"``, ``"checkstyle"``.
    file_extensions:
        List of file-name suffixes produced by this profile, e.g.
        ``[".py"]``, ``[".go"]``, ``[".rs"]``, ``[".ts", ".tsx"]``.
    docker_image:
        Base Docker image for containerised builds, e.g.
        ``"python:3.12-slim"``, ``"golang:1.22-alpine"``.
    system_prompt:
        The expert persona injected as the LLM system message when this
        profile's code-generation agent is invoked.
    test_command:
        Shell command that executes the full test suite, e.g. ``"pytest"``,
        ``"go test ./..."``, ``"cargo test"``, ``"npm test"``.
    build_command:
        Shell command that validates or compiles the project, e.g.
        ``"python -m py_compile"``, ``"go build ./..."``, ``"cargo build"``.
    """

    language: str
    framework: str
    package_manager: str
    test_runner: str
    lint_tool: str
    file_extensions: list[str]
    docker_image: str
    system_prompt: str
    test_command: str
    build_command: str
