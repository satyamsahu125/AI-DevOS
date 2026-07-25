"""
ProjectValidator — Phase 7 of AI DevOS.

After Backend and Frontend Developers write files to disk,
this validator:
  1. Installs dependencies
  2. Checks Python compilation
  3. Attempts project startup
  4. Runs generated tests
  5. Reports a structured ValidationResult

If startup fails, WorkflowManager feeds the error back to
BackendDeveloperAgent for a targeted fix (self-healing loop,
max 3 attempts).
"""

import ast
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    step: str
    passed: bool
    output: str = ""
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


@dataclass
class ValidationResult:
    project_id: str
    passed: bool
    steps: dict[str, StepResult]
    error_summary: str = ""
    fixable_errors: list[str] = field(default_factory=list)
    # Structured errors for self-healing loop
    startup_error: str | None = None
    compile_errors: list[dict] = field(default_factory=list)
    test_results: dict = field(default_factory=dict)


class ProjectValidator:
    """
    Validates that generated project files actually run.
    Called after all sprint stages complete.
    """

    INSTALL_TIMEOUT = 120   # seconds
    STARTUP_TIMEOUT = 15    # seconds
    TEST_TIMEOUT = 60       # seconds
    COMPILE_TIMEOUT = 30    # seconds

    def __init__(self, workspace_manager) -> None:
        self.workspace = workspace_manager

    def get_project_dir(self, project_id: str) -> Path:
        return self.workspace.get_workspace_path(project_id) / "project"

    def validate(
        self,
        project_id: str,
        skip_install: bool = False
    ) -> ValidationResult:
        """
        Run full validation suite.
        Returns ValidationResult with per-step details.
        """
        logger.info("ProjectValidator: starting validation for %s", project_id)
        project_dir = self.get_project_dir(project_id)

        if not project_dir.exists():
            return ValidationResult(
                project_id=project_id,
                passed=False,
                steps={},
                error_summary=(
                    f"Project directory not found: {project_dir}. "
                    "Backend/Frontend stages may not have run yet."
                ),
            )

        steps: dict[str, StepResult] = {}

        # Step 1: Install dependencies
        if not skip_install:
            steps["install"] = self._step_install(project_dir)
        else:
            steps["install"] = StepResult(
                step="install", passed=True, output="Skipped (skip_install=True)"
            )

        # Step 2: Compile Python files
        steps["compile"] = self._step_compile_python(project_dir)

        # Step 3: Attempt startup
        if steps["compile"].passed:
            steps["startup"] = self._step_startup(project_dir)
        else:
            steps["startup"] = StepResult(
                step="startup",
                passed=False,
                output="Skipped — compile errors must be fixed first",
                errors=["Compile failed"],
            )

        # Step 4: Run generated tests
        steps["tests"] = self._step_run_tests(project_dir)

        # Calculate overall result
        critical_steps = ["compile", "startup"]
        all_critical_pass = all(
            steps[s].passed for s in critical_steps if s in steps
        )
        passed = all_critical_pass

        # Build fixable error list for self-healing loop
        fixable_errors = []
        startup_error = None
        compile_errors = []

        if not steps["compile"].passed:
            compile_errors = [
                {"file": e.split(":")[0], "error": e}
                for e in steps["compile"].errors
            ]
            fixable_errors.extend(steps["compile"].errors[:5])

        if not steps["startup"].passed:
            startup_error = "\n".join(steps["startup"].errors[:10])
            fixable_errors.append(f"Startup failed: {startup_error[:500]}")

        error_summary = "; ".join(fixable_errors[:3]) if fixable_errors else ""

        result = ValidationResult(
            project_id=project_id,
            passed=passed,
            steps=steps,
            error_summary=error_summary,
            fixable_errors=fixable_errors,
            startup_error=startup_error,
            compile_errors=compile_errors,
            test_results={
                "total": steps["tests"].output.count("PASSED")
                + steps["tests"].output.count("FAILED"),
                "passed": steps["tests"].output.count("PASSED"),
                "failed": steps["tests"].output.count("FAILED"),
            },
        )

        logger.info(
            "ProjectValidator: %s — passed=%s "
            "install=%s compile=%s startup=%s tests=%s",
            project_id,
            result.passed,
            steps["install"].passed,
            steps["compile"].passed,
            steps["startup"].passed,
            steps["tests"].passed,
        )
        return result

    def _step_install(self, project_dir: Path) -> StepResult:
        """pip install -r requirements.txt"""
        import time

        req_file = project_dir / "backend" / "requirements.txt"

        if not req_file.exists():
            return StepResult(
                step="install", passed=True, output="No requirements.txt found — skipping"
            )

        start = time.time()
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "-r",
                    str(req_file),
                    "-q",
                    "--disable-pip-version-check",
                ],
                capture_output=True,
                text=True,
                timeout=self.INSTALL_TIMEOUT,
                cwd=str(project_dir),
            )
            duration = time.time() - start
            passed = result.returncode == 0
            return StepResult(
                step="install",
                passed=passed,
                output=result.stdout[:1000],
                errors=([result.stderr[:500]] if not passed else []),
                duration_seconds=round(duration, 2),
            )
        except subprocess.TimeoutExpired:
            return StepResult(
                step="install", passed=False, errors=[f"Timed out after {self.INSTALL_TIMEOUT}s"]
            )
        except Exception as e:
            return StepResult(step="install", passed=False, errors=[str(e)])

    def _step_compile_python(self, project_dir: Path) -> StepResult:
        """Parse every .py file with ast.parse to check syntax."""
        backend_dir = project_dir / "backend"
        if not backend_dir.exists():
            return StepResult(
                step="compile", passed=True, output="No backend directory — skipping"
            )

        errors = []
        checked = 0
        py_files = list(backend_dir.rglob("*.py"))

        for py_file in py_files:
            if "__pycache__" in str(py_file):
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                ast.parse(source, filename=str(py_file))
                checked += 1
            except SyntaxError as e:
                rel = py_file.relative_to(project_dir)
                errors.append(f"{rel}:{e.lineno}: SyntaxError: {e.msg}")
            except Exception as e:
                rel = py_file.relative_to(project_dir)
                errors.append(f"{rel}: {str(e)}")

        passed = len(errors) == 0
        return StepResult(
            step="compile",
            passed=passed,
            output=f"Checked {checked} Python files",
            errors=errors[:20],
        )

    def _step_startup(self, project_dir: Path) -> StepResult:
        """Attempt to start the backend server briefly."""
        import time

        main_candidates = [
            project_dir / "backend" / "main.py",
            project_dir / "backend" / "app" / "main.py",
            project_dir / "main.py",
        ]
        main_file = next((f for f in main_candidates if f.exists()), None)

        if not main_file:
            return StepResult(
                step="startup", passed=True, output="No main.py found — treating as pass"
            )

        start = time.time()
        try:
            cwd_dir = main_file.parent
            proc = subprocess.Popen(
                [sys.executable, str(main_file)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(cwd_dir),
                text=True,
            )

            try:
                stdout, stderr = proc.communicate(timeout=self.STARTUP_TIMEOUT)
                duration = time.time() - start
                # Process exited — could be error or clean exit
                passed = proc.returncode == 0
                errors = [stderr[:500]] if stderr and not passed else []
                return StepResult(
                    step="startup",
                    passed=passed,
                    output=stdout[:500],
                    errors=errors,
                    duration_seconds=round(duration, 2),
                )
            except subprocess.TimeoutExpired:
                # Still running after timeout = healthy startup
                proc.kill()
                proc.communicate()
                duration = time.time() - start
                return StepResult(
                    step="startup",
                    passed=True,
                    output=f"Process started and ran for {self.STARTUP_TIMEOUT}s without crashing",
                    duration_seconds=round(duration, 2),
                )
        except Exception as e:
            return StepResult(
                step="startup", passed=False, errors=[f"Failed to launch: {str(e)}"]
            )

    def _step_run_tests(self, project_dir: Path) -> StepResult:
        """Run pytest on generated test files."""
        import time

        tests_dir = project_dir / "tests"

        if not tests_dir.exists():
            return StepResult(step="tests", passed=True, output="No tests directory — skipping")

        test_files = list(tests_dir.glob("test_*.py"))
        if not test_files:
            return StepResult(step="tests", passed=True, output="No test files found — skipping")

        start = time.time()
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    str(tests_dir),
                    "-v",
                    "--tb=short",
                    "-q",
                    "--no-header",
                ],
                capture_output=True,
                text=True,
                timeout=self.TEST_TIMEOUT + 30,
                cwd=str(project_dir),
            )
            duration = time.time() - start
            output = (result.stdout + result.stderr)[:2000]
            passed = result.returncode == 0
            return StepResult(
                step="tests",
                passed=passed,
                output=output,
                errors=[] if passed else [output[-500:]],
                duration_seconds=round(duration, 2),
            )
        except subprocess.TimeoutExpired:
            return StepResult(
                step="tests", passed=False, errors=[f"Tests timed out after {self.TEST_TIMEOUT}s"]
            )
        except Exception as e:
            return StepResult(step="tests", passed=False, errors=[str(e)])
