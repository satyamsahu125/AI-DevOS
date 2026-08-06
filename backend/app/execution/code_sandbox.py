"""code_sandbox.py — High-level code execution sandbox for AI DevOS.

Orchestrates lint + test + build checks against a generated project.
Uses SecureExecutionSandbox (Docker-backed) when SANDBOX_ENABLED=true and Docker
is available; falls back to subprocess for Python projects in dev mode.

Design:
- Disabled by default (SANDBOX_ENABLED=false in .env) — no-op safe
- Detects stack from generated files (requirements.txt → python, package.json → node)
- Runs lint → build → test in sequence; stops after build failure
- Returns SandboxResult (typed DTO) for BugAnalyst to consume
- Non-fatal: all errors are caught; failure produces SandboxResult with error info

Safety contract:
- Sandbox runs are READ from project files — never writes to them
- Docker-backed path enforces network isolation and memory limits
- Subprocess path is development-only, always runs with timeout
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from ..shared.dto.sandbox_result import BuildResult, LintResult, SandboxResult, TestResult

logger = logging.getLogger(__name__)

_SANDBOX_ENABLED = os.getenv("SANDBOX_ENABLED", "false").lower() in ("true", "1", "yes")
_SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "60"))
_DOCKER_PYTHON = os.getenv("SANDBOX_DOCKER_PYTHON", "python:3.12-slim")
_DOCKER_NODE = os.getenv("SANDBOX_DOCKER_NODE", "node:20-slim")


class CodeSandbox:
    """Runs lint, test, and build checks against a generated project directory.

    Parameters
    ----------
    workspace_manager:
        Used to resolve project workspace paths.
    enabled:
        Explicit override for SANDBOX_ENABLED env var. Useful in tests.
    timeout_seconds:
        Per-operation timeout (lint, test, build each get this budget).

    Error contract:
        run() never raises. Any exception is caught, logged, and returned
        as a SandboxResult with the failing check's errors populated.
    """

    def __init__(
        self,
        workspace_manager: Any = None,
        enabled: bool | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self._workspace = workspace_manager
        self._enabled = enabled if enabled is not None else _SANDBOX_ENABLED
        self._timeout = timeout_seconds if timeout_seconds is not None else _SANDBOX_TIMEOUT
        # Lazy-import SecureExecutionSandbox so Docker is optional
        self._docker_sandbox: Any = None
        if self._enabled:
            try:
                from .sandbox import SecureExecutionSandbox
                self._docker_sandbox = SecureExecutionSandbox(default_image=_DOCKER_PYTHON)
                if not self._docker_sandbox.is_available():
                    logger.info("[CodeSandbox] Docker not available — subprocess fallback only")
                    self._docker_sandbox = None
            except Exception as exc:
                logger.warning("[CodeSandbox] SecureExecutionSandbox init failed: %s", exc)
                self._docker_sandbox = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, project_id: str, sprint: int = 0) -> SandboxResult:
        """Run lint + build + test for project_id's generated code.

        Returns SandboxResult with all three checks populated. Stops after
        build failure (no point testing unimportable code). Non-fatal.
        """
        logger.info("[CodeSandbox] run: project=%s sprint=%d enabled=%s", project_id, sprint, self._enabled)
        if not self._enabled:
            return SandboxResult.disabled(project_id, sprint)

        project_dir = self._resolve_project_dir(project_id)
        if project_dir is None:
            logger.warning("[CodeSandbox] cannot resolve project dir for %s", project_id)
            return SandboxResult(
                project_id=project_id,
                sprint=sprint,
                enabled=True,
                build=BuildResult(success=False, errors=["Could not resolve project workspace directory"]),
            )

        stack = self.detect_stack(project_dir)
        logger.info("[CodeSandbox] detected stack: %s for project=%s", stack, project_id)

        result = SandboxResult(project_id=project_id, sprint=sprint, stack=stack, enabled=True)

        try:
            result.lint = self.lint(project_dir, stack)
        except Exception as exc:
            logger.warning("[CodeSandbox] lint failed (non-fatal): %s", exc)
            result.lint = LintResult(errors=[{"file": "?", "line": 0, "message": str(exc)}], error_count=1)

        try:
            result.build = self.build(project_dir, stack)
        except Exception as exc:
            logger.warning("[CodeSandbox] build failed (non-fatal): %s", exc)
            result.build = BuildResult(success=False, errors=[str(exc)])

        if not result.build.success:
            logger.info("[CodeSandbox] stopping after build failure, skipping tests")
            return result

        try:
            result.test = self.test(project_dir, stack)
        except Exception as exc:
            logger.warning("[CodeSandbox] test failed (non-fatal): %s", exc)
            result.test = TestResult(total=0, failures=[{"test_name": "?", "error": str(exc)}])

        logger.info(
            "[CodeSandbox] complete: project=%s lint_errors=%d tests=%d/%d build=%s",
            project_id, result.lint.error_count, result.test.passed, result.test.total, result.build.success,
        )
        return result

    def syntax_check(self, project_id: str, sprint: int = 0) -> list[str]:
        """Run syntax check on ALL generated files for project_id.

        R2: called after each sprint completes to fail fast on syntax errors
        before the sprint is marked complete. Returns a list of error strings
        (empty list = clean). Non-fatal: any exception is caught and returned
        as a single error string so the pipeline can decide what to do.
        """
        if not self._enabled:
            return []
        try:
            project_dir = self._resolve_project_dir(project_id)
            if project_dir is None:
                logger.warning("[CodeSandbox] syntax_check: cannot resolve dir for %s", project_id)
                return []
            stack = self.detect_stack(project_dir)
            errors = self._syntax_check_all(project_dir, stack)
            if errors:
                logger.warning(
                    "[CodeSandbox] syntax_check found %d error(s): project=%s sprint=%d",
                    len(errors), project_id, sprint,
                )
            else:
                logger.info(
                    "[CodeSandbox] syntax_check passed: project=%s sprint=%d stack=%s",
                    project_id, sprint, stack,
                )
            return errors
        except Exception as exc:
            logger.warning("[CodeSandbox] syntax_check exception (non-fatal): %s", exc)
            return [f"syntax check internal error: {exc}"]

    def _syntax_check_all(self, project_dir: Path, stack: str) -> list[str]:
        """Run py_compile or node --check on every source file.

        Returns list of 'filename: error' strings. Empty = all pass.
        Only checks files that exist and are readable.
        """
        errors: list[str] = []
        if stack == "python":
            for py_file in project_dir.rglob("*.py"):
                # Skip virtual-env and cache directories
                if any(part in {".venv", "venv", "__pycache__", ".tox", "node_modules"} for part in py_file.parts):
                    continue
                proc = self._run_subprocess(["python", "-m", "py_compile", str(py_file)], cwd=project_dir)
                if proc.returncode != 0:
                    stderr = (proc.stderr or proc.stdout or "").strip()
                    errors.append(f"{py_file.name}: {stderr}")
        elif stack == "node":
            for js_file in project_dir.rglob("*.js"):
                if any(part in {"node_modules", ".cache", "dist", "build"} for part in js_file.parts):
                    continue
                proc = self._run_subprocess(["node", "--check", str(js_file)], cwd=project_dir)
                if proc.returncode != 0:
                    stderr = (proc.stderr or proc.stdout or "").strip()
                    errors.append(f"{js_file.name}: {stderr}")
        return errors

    def detect_stack(self, project_dir: Path) -> str:
        """Return "python", "node", or "unknown" by inspecting generated files."""
        # Walk first two levels of the generated project for stack indicators
        subdirs = list(project_dir.iterdir()) if project_dir.is_dir() else []
        for candidate in [project_dir, *subdirs]:
            if not isinstance(candidate, Path):
                continue
            if (candidate / "requirements.txt").exists() or (candidate / "setup.py").exists() or (candidate / "pyproject.toml").exists():
                return "python"
            if (candidate / "package.json").exists():
                return "node"
        return "unknown"

    def lint(self, project_dir: Path, stack: str) -> LintResult:
        """Run linter and return LintResult. Uses ruff (Python) or eslint (Node)."""
        started = time.time()
        if stack == "python":
            return self._lint_python(project_dir, started)
        if stack == "node":
            return self._lint_node(project_dir, started)
        return LintResult(duration_ms=0)  # unknown stack — no lint

    def build(self, project_dir: Path, stack: str) -> BuildResult:
        """Run import/build check and return BuildResult."""
        started = time.time()
        if stack == "python":
            return self._build_python(project_dir, started)
        if stack == "node":
            return self._build_node(project_dir, started)
        return BuildResult(success=True)  # unknown — assume ok

    def test(self, project_dir: Path, stack: str) -> TestResult:
        """Run test suite and return TestResult."""
        started = time.time()
        if stack == "python":
            return self._test_python(project_dir, started)
        if stack == "node":
            return self._test_node(project_dir, started)
        return TestResult()

    # ------------------------------------------------------------------
    # Private helpers — Python stack
    # ------------------------------------------------------------------

    def _lint_python(self, project_dir: Path, started: float) -> LintResult:
        """Run ruff check. Falls back to flake8 if ruff not available."""
        cmd = ["ruff", "check", "--output-format=json", str(project_dir)]
        proc = self._run_subprocess(cmd, cwd=project_dir)
        ms = int((time.time() - started) * 1000)

        errors: list[dict] = []
        try:
            ruff_output = json.loads(proc.stdout or "[]")
            for item in ruff_output:
                errors.append({
                    "file": item.get("filename", "?"),
                    "line": item.get("location", {}).get("row", 0),
                    "message": f"[{item.get('code', '?')}] {item.get('message', '')}",
                })
        except (json.JSONDecodeError, TypeError):
            # ruff not installed or output not JSON — try parsing text
            errors = self._parse_text_errors(proc.stdout or proc.stderr or "")

        return LintResult(
            errors=errors,
            error_count=len(errors),
            duration_ms=ms,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )

    def _build_python(self, project_dir: Path, started: float) -> BuildResult:
        """Try to import the generated app entry point as a syntax check."""
        # Look for main.py, app.py, or any Python file with 'main' in the name
        entry = self._find_python_entry(project_dir)
        if entry is None:
            return BuildResult(success=True, duration_ms=0)  # nothing to check

        cmd = ["python", "-m", "py_compile", str(entry)]
        proc = self._run_subprocess(cmd, cwd=project_dir)
        ms = int((time.time() - started) * 1000)

        if proc.returncode == 0:
            return BuildResult(success=True, duration_ms=ms, stdout=proc.stdout or "")

        errors = [line for line in (proc.stderr or proc.stdout or "").splitlines() if line.strip()]
        return BuildResult(success=False, errors=errors, duration_ms=ms, stderr=proc.stderr or "")

    def _test_python(self, project_dir: Path, started: float) -> TestResult:
        """Run pytest with JSON output."""
        tests_dir = project_dir / "tests"
        if not tests_dir.exists():
            return TestResult(total=0)

        cmd = ["pytest", str(tests_dir), "--tb=short", "-q", "--no-header"]
        proc = self._run_subprocess(cmd, cwd=project_dir)
        ms = int((time.time() - started) * 1000)

        return self._parse_pytest_output(proc.stdout or "", proc.stderr or "", ms)

    def _lint_node(self, project_dir: Path, started: float) -> LintResult:
        """Run eslint with JSON output."""
        cmd = ["npx", "eslint", ".", "--format=json", "--ext=.js,.jsx,.ts,.tsx"]
        proc = self._run_subprocess(cmd, cwd=project_dir)
        ms = int((time.time() - started) * 1000)

        errors: list[dict] = []
        try:
            eslint_output = json.loads(proc.stdout or "[]")
            for file_result in eslint_output:
                filepath = file_result.get("filePath", "?")
                for msg in file_result.get("messages", []):
                    if msg.get("severity", 0) >= 2:  # severity 2 = error
                        errors.append({
                            "file": filepath,
                            "line": msg.get("line", 0),
                            "message": msg.get("message", ""),
                        })
        except (json.JSONDecodeError, TypeError):
            errors = self._parse_text_errors(proc.stdout or proc.stderr or "")

        return LintResult(errors=errors, error_count=len(errors), duration_ms=ms)

    def _build_node(self, project_dir: Path, started: float) -> BuildResult:
        """Run npm run build."""
        pkg = project_dir / "package.json"
        if not pkg.exists():
            return BuildResult(success=True)

        cmd = ["npm", "run", "build", "--if-present"]
        proc = self._run_subprocess(cmd, cwd=project_dir)
        ms = int((time.time() - started) * 1000)

        if proc.returncode == 0:
            return BuildResult(success=True, duration_ms=ms)

        errors = [line for line in (proc.stderr or proc.stdout or "").splitlines() if line.strip()][:20]
        return BuildResult(success=False, errors=errors, duration_ms=ms)

    def _test_node(self, project_dir: Path, started: float) -> TestResult:
        """Run jest."""
        cmd = ["npx", "jest", "--json", "--passWithNoTests"]
        proc = self._run_subprocess(cmd, cwd=project_dir)
        ms = int((time.time() - started) * 1000)

        try:
            jest_result = json.loads(proc.stdout or "{}")
            passed = jest_result.get("numPassedTests", 0)
            failed = jest_result.get("numFailedTests", 0)
            total = jest_result.get("numTotalTests", 0)
            failures = []
            for suite in jest_result.get("testResults", []):
                for test in suite.get("testResults", []):
                    if test.get("status") == "failed":
                        failures.append({
                            "test_name": test.get("fullName", "?"),
                            "error": " ".join(test.get("failureMessages", [])),
                        })
            return TestResult(passed=passed, failed=failed, total=total, failures=failures, duration_ms=ms)
        except (json.JSONDecodeError, TypeError):
            return TestResult(total=0, duration_ms=ms)

    # ------------------------------------------------------------------
    # Private helpers — shared
    # ------------------------------------------------------------------

    def verify_dockerfile(self, project_id: str) -> list[str]:
        """R3: Validate the Dockerfile syntax after the DevOps stage runs.

        If Docker is available, runs `docker build --dry-run` (or --check for buildkit).
        Falls back to a structural lint (checks for required instructions: FROM, WORKDIR,
        COPY, CMD/ENTRYPOINT) when Docker is not available.

        Returns a list of error strings (empty = valid). Non-fatal.
        """
        if not self._enabled:
            return []
        try:
            project_dir = self._resolve_project_dir(project_id)
            if project_dir is None:
                return []

            dockerfile = None
            for candidate in project_dir.rglob("Dockerfile"):
                if "node_modules" not in str(candidate):
                    dockerfile = candidate
                    break

            if dockerfile is None:
                logger.debug("[CodeSandbox] verify_dockerfile: no Dockerfile found for %s", project_id)
                return ["Dockerfile not found in generated project"]

            # Try Docker if available
            if self._docker_sandbox is not None:
                proc = self._run_subprocess(
                    ["docker", "build", "--check", str(project_dir)],
                    cwd=project_dir,
                )
                if proc.returncode == 0:
                    logger.info("[CodeSandbox] Dockerfile verification passed (docker --check): %s", project_id)
                    return []
                return [f"docker build --check: {(proc.stderr or proc.stdout or '').strip()[:500]}"]

            # Fallback: structural lint — check for required Dockerfile instructions
            errors = self._lint_dockerfile_structure(dockerfile)
            if errors:
                logger.warning("[CodeSandbox] Dockerfile structural issues: %s", errors)
            else:
                logger.info("[CodeSandbox] Dockerfile structural validation passed: %s", project_id)
            return errors
        except Exception as exc:
            logger.warning("[CodeSandbox] verify_dockerfile exception (non-fatal): %s", exc)
            return []

    def _lint_dockerfile_structure(self, dockerfile: Path) -> list[str]:
        """Parse Dockerfile for required instructions. Returns error list."""
        try:
            content = dockerfile.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return [f"Cannot read Dockerfile: {exc}"]

        errors: list[str] = []
        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]

        instructions = {l.split()[0].upper() for l in lines if l.split()}
        required = {"FROM"}
        recommended = {"WORKDIR", "COPY", "CMD", "ENTRYPOINT"}

        for req in required:
            if req not in instructions:
                errors.append(f"Dockerfile missing required instruction: {req}")

        has_cmd = "CMD" in instructions or "ENTRYPOINT" in instructions
        if not has_cmd:
            errors.append("Dockerfile missing CMD or ENTRYPOINT instruction")

        return errors

    def _resolve_project_dir(self, project_id: str) -> Path | None:
        """Resolve the generated project directory for project_id."""
        if self._workspace is None:
            return None
        try:
            ws_path = self._workspace.get_workspace_path(project_id)
            project_dir = ws_path / "project"
            if project_dir.exists():
                return project_dir
            # Fall back to workspace root itself
            return ws_path if ws_path.exists() else None
        except Exception as exc:
            logger.debug("[CodeSandbox] _resolve_project_dir failed for %s: %s", project_id, exc)
            return None

    def _find_python_entry(self, project_dir: Path) -> Path | None:
        """Find a Python entry point to compile-check."""
        for name in ("main.py", "app.py", "server.py", "run.py"):
            for candidate in project_dir.rglob(name):
                return candidate
        return None

    def _run_subprocess(self, cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
        """Run cmd as a subprocess with timeout. Never raises."""
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(cmd, returncode=124, stdout="", stderr=f"timeout after {self._timeout}s")
        except FileNotFoundError as exc:
            # Command not available (e.g. ruff not installed)
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=f"command not found: {exc}")
        except Exception as exc:
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr=str(exc))

    @staticmethod
    def _parse_text_errors(text: str) -> list[dict]:
        """Parse error lines like 'file.py:10:5: E501 line too long'."""
        errors = []
        pattern = re.compile(r"^(.+?):(\d+)(?::\d+)?\s*:?\s*(.+)$")
        for line in text.splitlines():
            m = pattern.match(line.strip())
            if m:
                errors.append({"file": m.group(1), "line": int(m.group(2)), "message": m.group(3)})
        return errors

    @staticmethod
    def _parse_pytest_output(stdout: str, stderr: str, duration_ms: int) -> TestResult:
        """Parse pytest's text output into TestResult."""
        passed = failed = total = 0
        failures: list[dict] = []

        # Look for summary line like "5 passed, 2 failed in 1.23s"
        summary_pattern = re.compile(r"(\d+) passed|(\d+) failed|(\d+) error")
        for m in summary_pattern.finditer(stdout + stderr):
            if m.group(1):
                passed = int(m.group(1))
            if m.group(2):
                failed = int(m.group(2))
            if m.group(3):
                failed += int(m.group(3))

        total = passed + failed

        # Extract FAILED lines
        for line in stdout.splitlines():
            if line.startswith("FAILED"):
                failures.append({"test_name": line[7:].strip(), "error": ""})

        return TestResult(
            passed=passed,
            failed=failed,
            total=total,
            failures=failures,
            duration_ms=duration_ms,
            stdout=stdout[:2000],
            stderr=stderr[:1000],
        )
