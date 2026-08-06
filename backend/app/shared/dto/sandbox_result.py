from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class LintResult:
    """Output from a linter run (ruff for Python, eslint for Node).

    errors is a list of dicts, each with keys: file, line, message.
    error_count is the total number of errors across all files.
    duration_ms is the wall-clock time of the lint run.
    """

    errors: list[dict] = field(default_factory=list)
    error_count: int = 0
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""

    def to_prompt_text(self) -> str:
        if not self.errors:
            return "Lint: PASS (0 errors)"
        lines = [f"Lint: {self.error_count} error(s)"]
        for err in self.errors[:20]:  # cap at 20 to avoid token overflow
            file_info = err.get("file", "")
            line_info = err.get("line", "")
            msg = err.get("message", "")
            lines.append(f"  {file_info}:{line_info}: {msg}")
        if len(self.errors) > 20:
            lines.append(f"  ... and {len(self.errors) - 20} more")
        return "\n".join(lines)


@dataclass
class TestResult:
    """Output from a test run (pytest for Python, jest for Node).

    failures is a list of dicts, each with keys: test_name, error.
    """

    passed: int = 0
    failed: int = 0
    total: int = 0
    failures: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""

    def to_prompt_text(self) -> str:
        if self.total == 0:
            return "Tests: NO TESTS FOUND"
        status = "PASS" if self.failed == 0 else "FAIL"
        lines = [f"Tests: {status} — {self.passed}/{self.total} passed"]
        for f in self.failures[:10]:
            lines.append(f"  FAILED: {f.get('test_name', '?')}: {f.get('error', '')[:200]}")
        return "\n".join(lines)


@dataclass
class BuildResult:
    """Output from a build/import check (python -c import or npm run build)."""

    success: bool = True
    errors: list[str] = field(default_factory=list)
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""

    def to_prompt_text(self) -> str:
        if self.success:
            return "Build: OK"
        lines = ["Build: FAILED"]
        for err in self.errors[:10]:
            lines.append(f"  {err[:300]}")
        return "\n".join(lines)


@dataclass
class SandboxResult:
    """Aggregated result from a full sandbox run (lint + tests + build).

    Produced by CodeSandbox.run() and stored at memory key "sandbox:latest".
    Consumed by BugAnalyst to ground its analysis in real execution results.
    """

    project_id: str
    sprint: int
    ran_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stack: str = "unknown"              # "python" | "node" | "unknown"
    enabled: bool = True                # False when SANDBOX_ENABLED=false
    lint: LintResult = field(default_factory=LintResult)
    test: TestResult = field(default_factory=TestResult)
    build: BuildResult = field(default_factory=BuildResult)

    def to_json(self) -> str:
        """Serialize to JSON string for storage in MemoryManager."""
        return json.dumps(self._to_dict(), indent=2)

    def to_prompt_text(self) -> str:
        """Render a compact text summary for BugAnalyst's prompt context."""
        if not self.enabled:
            return "Sandbox: DISABLED (SANDBOX_ENABLED=false)"
        lines = [
            f"Sandbox results — Sprint {self.sprint} ({self.stack} stack):",
            f"  {self.lint.to_prompt_text()}",
            f"  {self.test.to_prompt_text()}",
            f"  {self.build.to_prompt_text()}",
        ]
        return "\n".join(lines)

    def _to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "sprint": self.sprint,
            "ran_at": self.ran_at,
            "stack": self.stack,
            "enabled": self.enabled,
            "lint": {
                "errors": self.lint.errors,
                "error_count": self.lint.error_count,
                "duration_ms": self.lint.duration_ms,
            },
            "test": {
                "passed": self.test.passed,
                "failed": self.test.failed,
                "total": self.test.total,
                "failures": self.test.failures,
                "duration_ms": self.test.duration_ms,
            },
            "build": {
                "success": self.build.success,
                "errors": self.build.errors,
                "duration_ms": self.build.duration_ms,
            },
        }

    @classmethod
    def disabled(cls, project_id: str, sprint: int) -> "SandboxResult":
        """Return a result indicating sandbox was disabled — no execution ran."""
        return cls(project_id=project_id, sprint=sprint, enabled=False)
