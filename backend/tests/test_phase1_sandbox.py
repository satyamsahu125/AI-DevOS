"""test_phase1_sandbox.py — Phase 1 acceptance-criteria tests.

Covers AC-01 through AC-09 without requiring Docker, real pip/npm, or a live
Bedrock connection.  All subprocess calls are mocked at the
CodeSandbox._run_subprocess boundary so tests are deterministic and fast.

Running:
    cd backend
    python -m pytest tests/test_phase1_sandbox.py -v
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_proc(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _make_sandbox(enabled: bool = True, workspace=None) -> "CodeSandbox":
    """Build a CodeSandbox instance with Docker disabled (subprocess only)."""
    from app.execution.code_sandbox import CodeSandbox
    sb = CodeSandbox(workspace_manager=workspace, enabled=enabled, timeout_seconds=5)
    sb._docker_sandbox = None  # force subprocess path
    return sb


def _python_project(tmp_path: Path) -> Path:
    """Create a minimal Python project tree in tmp_path."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text("flask==3.0.0\n")
    (project / "main.py").write_text("print('hello')\n")
    tests = project / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_ok(): assert 1 == 1\n")
    return project


def _node_project(tmp_path: Path) -> Path:
    """Create a minimal Node project tree in tmp_path."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text('{"name":"test","scripts":{"build":"echo ok"}}\n')
    (project / "index.js").write_text("console.log('hello');\n")
    return project


# ---------------------------------------------------------------------------
# AC-01 — install() method exists and is callable
# ---------------------------------------------------------------------------

class TestInstallMethodExists:
    def test_codesandbox_has_install_method(self):
        """AC-01: CodeSandbox must expose an install() method."""
        from app.execution.code_sandbox import CodeSandbox
        assert callable(getattr(CodeSandbox, "install", None)), (
            "CodeSandbox.install() not found — AC-01 violated"
        )

    def test_install_returns_build_result(self, tmp_path):
        """AC-01: install() must return a BuildResult."""
        from app.shared.dto.sandbox_result import BuildResult
        sb = _make_sandbox()
        project = _python_project(tmp_path)

        with patch.object(sb, "_run_subprocess", return_value=_make_proc(0, "Successfully installed")) as mock_sub:
            result = sb.install(project, "python")

        assert isinstance(result, BuildResult)

    def test_install_unknown_stack_returns_success(self, tmp_path):
        """AC-01: install() on unknown stack is a no-op (returns success)."""
        from app.shared.dto.sandbox_result import BuildResult
        sb = _make_sandbox()
        project = tmp_path / "proj"
        project.mkdir()
        result = sb.install(project, "unknown")
        assert isinstance(result, BuildResult)
        assert result.success is True


# ---------------------------------------------------------------------------
# AC-02 — Python dependency installation calls pip
# ---------------------------------------------------------------------------

class TestPythonInstall:
    def test_install_python_calls_pip(self, tmp_path):
        """AC-02: pip install -r requirements.txt is invoked for Python stack."""
        sb = _make_sandbox()
        project = _python_project(tmp_path)

        with patch.object(sb, "_run_subprocess", return_value=_make_proc(0)) as mock_sub:
            result = sb.install(project, "python")

        assert result.success is True
        called_cmd = mock_sub.call_args[0][0]
        assert "pip" in called_cmd
        assert "install" in called_cmd
        assert any("requirements.txt" in str(a) for a in called_cmd)

    def test_install_python_failure_returns_failed_build_result(self, tmp_path):
        """AC-02: pip failure → BuildResult(success=False) with error details."""
        sb = _make_sandbox()
        project = _python_project(tmp_path)

        with patch.object(sb, "_run_subprocess", return_value=_make_proc(1, stderr="No module named 'fakepkg'")):
            result = sb.install(project, "python")

        assert result.success is False
        assert len(result.errors) > 0

    def test_install_python_no_requirements_skips_pip(self, tmp_path):
        """AC-02: No requirements.txt → install() succeeds without calling pip."""
        sb = _make_sandbox()
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("x = 1\n")

        with patch.object(sb, "_run_subprocess") as mock_sub:
            result = sb.install(project, "python")

        mock_sub.assert_not_called()
        assert result.success is True


# ---------------------------------------------------------------------------
# AC-03 — Node dependency installation calls npm
# ---------------------------------------------------------------------------

class TestNodeInstall:
    def test_install_node_calls_npm(self, tmp_path):
        """AC-03: npm install is invoked for Node stack."""
        sb = _make_sandbox()
        project = _node_project(tmp_path)

        with patch.object(sb, "_run_subprocess", return_value=_make_proc(0)) as mock_sub:
            result = sb.install(project, "node")

        assert result.success is True
        called_cmd = mock_sub.call_args[0][0]
        assert "npm" in called_cmd
        assert "install" in called_cmd

    def test_install_node_failure_returns_failed_build_result(self, tmp_path):
        """AC-03: npm install failure → BuildResult(success=False)."""
        sb = _make_sandbox()
        project = _node_project(tmp_path)

        with patch.object(sb, "_run_subprocess", return_value=_make_proc(1, stderr="npm ERR! 404 Not Found")):
            result = sb.install(project, "node")

        assert result.success is False


# ---------------------------------------------------------------------------
# AC-04 — run() calls install before lint/build/test (correct order)
# ---------------------------------------------------------------------------

class TestRunCallOrder:
    def test_run_calls_install_before_lint_and_build(self, tmp_path):
        """AC-04: run() order must be install → lint → build → test."""
        sb = _make_sandbox()
        project = _python_project(tmp_path)

        call_order: list[str] = []

        def _track_install(p, stack):
            call_order.append("install")
            from app.shared.dto.sandbox_result import BuildResult
            return BuildResult(success=True)

        def _track_lint(p, stack):
            call_order.append("lint")
            from app.shared.dto.sandbox_result import LintResult
            return LintResult()

        def _track_build(p, stack):
            call_order.append("build")
            from app.shared.dto.sandbox_result import BuildResult
            return BuildResult(success=True)

        def _track_test(p, stack):
            call_order.append("test")
            from app.shared.dto.sandbox_result import TestResult
            return TestResult(passed=1, total=1)

        # Patch workspace to return our project dir
        mock_ws = MagicMock()
        mock_ws.get_workspace_path.return_value = tmp_path
        sb._workspace = mock_ws

        with patch.object(sb, "install", side_effect=_track_install), \
             patch.object(sb, "lint",    side_effect=_track_lint), \
             patch.object(sb, "build",   side_effect=_track_build), \
             patch.object(sb, "test",    side_effect=_track_test):
            result = sb.run("test-project", sprint=1, require_execution=True)

        assert call_order == ["install", "lint", "build", "test"], (
            f"Unexpected call order: {call_order}"
        )

    def test_run_stops_after_install_failure(self, tmp_path):
        """AC-04: install failure → lint/build/test are never called."""
        sb = _make_sandbox()
        project = _python_project(tmp_path)

        from app.shared.dto.sandbox_result import BuildResult

        mock_ws = MagicMock()
        mock_ws.get_workspace_path.return_value = tmp_path
        sb._workspace = mock_ws

        lint_called = []
        build_called = []
        test_called = []

        with patch.object(sb, "install", return_value=BuildResult(success=False, errors=["pip failed"])), \
             patch.object(sb, "lint",    side_effect=lambda p, s: lint_called.append(1) or None), \
             patch.object(sb, "build",   side_effect=lambda p, s: build_called.append(1) or None), \
             patch.object(sb, "test",    side_effect=lambda p, s: test_called.append(1) or None):
            result = sb.run("test-project", sprint=1, require_execution=True)

        assert not result.build.success, "install failure should propagate as build failure"
        assert lint_called == [], "lint should not be called after install failure"
        assert build_called == [], "build should not be called after install failure"
        assert test_called == [], "test should not be called after install failure"


# ---------------------------------------------------------------------------
# AC-05 — SANDBOX_ENABLED=false + require_execution=True still runs
# ---------------------------------------------------------------------------

class TestRequireExecution:
    def test_disabled_sandbox_without_require_execution_returns_disabled(self, tmp_path):
        """SANDBOX_ENABLED=false without require_execution → disabled result (backward compat)."""
        from app.shared.dto.sandbox_result import SandboxResult
        sb = _make_sandbox(enabled=False)
        mock_ws = MagicMock()
        mock_ws.get_workspace_path.return_value = tmp_path
        sb._workspace = mock_ws

        result = sb.run("test-project", sprint=1, require_execution=False)
        assert isinstance(result, SandboxResult)
        assert result.enabled is False

    def test_disabled_sandbox_with_require_execution_runs(self, tmp_path):
        """AC-05: require_execution=True bypasses SANDBOX_ENABLED=false."""
        sb = _make_sandbox(enabled=False)
        project = _python_project(tmp_path)

        mock_ws = MagicMock()
        mock_ws.get_workspace_path.return_value = tmp_path
        sb._workspace = mock_ws

        from app.shared.dto.sandbox_result import BuildResult, LintResult, TestResult

        with patch.object(sb, "install", return_value=BuildResult(success=True)), \
             patch.object(sb, "lint",    return_value=LintResult()), \
             patch.object(sb, "build",   return_value=BuildResult(success=True)), \
             patch.object(sb, "test",    return_value=TestResult(passed=1, total=1)):
            result = sb.run("test-project", sprint=1, require_execution=True)

        assert result.enabled is True
        assert result.build.success is True


# ---------------------------------------------------------------------------
# AC-04 / AC-09 — SandboxResult.from_dict round-trip
# ---------------------------------------------------------------------------

class TestSandboxResultPersistence:
    def test_sandbox_result_round_trips_via_dict(self):
        """AC-09: SandboxResult._to_dict() + from_dict() round-trip is lossless."""
        from app.shared.dto.sandbox_result import BuildResult, LintResult, SandboxResult, TestResult

        original = SandboxResult(
            project_id="proj-1",
            sprint=2,
            stack="python",
            enabled=True,
            install=BuildResult(success=True, duration_ms=1200),
            lint=LintResult(error_count=1, errors=[{"file": "x.py", "line": 3, "message": "E501"}]),
            build=BuildResult(success=True, duration_ms=800),
            test=TestResult(passed=5, failed=1, total=6, failures=[{"test_name": "test_x", "error": "AssertionError"}]),
        )
        data = original._to_dict()
        restored = SandboxResult.from_dict(data)

        assert restored.project_id == original.project_id
        assert restored.sprint == original.sprint
        assert restored.stack == original.stack
        assert restored.install.success == original.install.success
        assert restored.install.duration_ms == original.install.duration_ms
        assert restored.build.success == original.build.success
        assert restored.test.passed == original.test.passed
        assert restored.test.failed == original.test.failed
        assert restored.lint.error_count == original.lint.error_count

    def test_sandbox_result_from_dict_tolerates_missing_install_field(self):
        """AC-09: Old persisted results without install field load without error."""
        from app.shared.dto.sandbox_result import SandboxResult

        # Simulate a dict saved before the install field was added
        old_data = {
            "project_id": "proj-old",
            "sprint": 1,
            "stack": "python",
            "enabled": True,
            "lint": {"errors": [], "error_count": 0, "duration_ms": 0},
            "build": {"success": True, "errors": [], "duration_ms": 0},
            "test": {"passed": 2, "failed": 0, "total": 2, "failures": [], "duration_ms": 0},
        }
        result = SandboxResult.from_dict(old_data)
        assert result.project_id == "proj-old"
        assert result.install.success is True  # safe default


# ---------------------------------------------------------------------------
# AC-05 — SprintExecutor gates sprint completion on sandbox build result
# ---------------------------------------------------------------------------

class TestSprintExecutorSandboxGate:
    """Verify that SprintExecutor.run() returns success=False when build fails."""

    def _build_executor(self, sandbox):
        """Create a minimal SprintExecutor with enough fakes to call run()."""
        from app.workflow.sprint_executor import SprintExecutor
        from app.shared.dto.sandbox_result import BuildResult, SandboxResult

        # Engine always returns success for all stages
        mock_engine = MagicMock()
        mock_engine.run.return_value = MagicMock(success=True, message="ok")

        # Workspace
        mock_ws = MagicMock()
        mock_ws.set_current_sprint.return_value = None
        mock_ws.create_sprint_folder.return_value = None
        mock_ws.mark_sprint_complete.return_value = None
        mock_ws.update_project_json.return_value = None
        mock_ws.get_workspace_path.return_value = Path("/tmp/fake-ws")
        mock_artifact_store = MagicMock()
        mock_artifact_store.exists.return_value = False
        mock_artifact_store.write.return_value = None
        mock_ws.get_artifact_store.return_value = mock_artifact_store

        # ArtifactManager
        mock_am = MagicMock()
        mock_am.get_artifact.return_value = None

        return SprintExecutor(
            engine=mock_engine,
            agent_factory=MagicMock(),
            workspace_manager=mock_ws,
            artifact_manager=mock_am,
            code_sandbox=sandbox,
        )

    def _make_sprint(self):
        from app.shared.models.sprint import Sprint
        return Sprint(
            sprint_id="00000000-0000-0000-0000-000000000001",
            sprint_number=1,
            name="Sprint 1",
            goal="Build MVP",
            features=["login"],
        )

    def test_build_failure_causes_sprint_failure(self, tmp_path):
        """AC-05: build failure → SprintResult(success=False); mark_sprint_complete not called."""
        from app.shared.dto.sandbox_result import BuildResult, SandboxResult
        from app.shared.schemas.file_plan_schema import FilePlan

        # Sandbox whose build fails
        mock_sandbox = MagicMock()
        mock_sandbox.run.return_value = SandboxResult(
            project_id="proj-1",
            sprint=1,
            enabled=True,
            install=BuildResult(success=True),
            build=BuildResult(success=False, errors=["ImportError: no module 'fastapi'"]),
        )

        executor = self._build_executor(mock_sandbox)
        sprint = self._make_sprint()

        # Patch _load_file_plan so it doesn't read real files
        with patch.object(executor, "_load_file_plan", return_value=FilePlan(project_id="proj-1", sprint_number=1)), \
             patch.object(executor, "_run_scrum_master"), \
             patch.object(executor, "_run_sprint_delta"):
            result = executor.run("proj-1", sprint)

        assert result.success is False, "Sprint must fail when build fails (AC-05)"
        executor._workspace.mark_sprint_complete.assert_not_called()

    def test_build_success_marks_sprint_complete(self, tmp_path):
        """AC-05: build+test success → mark_sprint_complete IS called."""
        from app.shared.dto.sandbox_result import BuildResult, SandboxResult, TestResult
        from app.shared.schemas.file_plan_schema import FilePlan

        mock_sandbox = MagicMock()
        mock_sandbox.run.return_value = SandboxResult(
            project_id="proj-1",
            sprint=1,
            enabled=True,
            install=BuildResult(success=True),
            build=BuildResult(success=True),
            test=TestResult(passed=3, total=3),
        )

        executor = self._build_executor(mock_sandbox)
        sprint = self._make_sprint()

        with patch.object(executor, "_load_file_plan", return_value=FilePlan(project_id="proj-1", sprint_number=1)), \
             patch.object(executor, "_run_scrum_master"), \
             patch.object(executor, "_run_sprint_delta"), \
             patch.object(executor, "_run_sprint_deploy_and_review"), \
             patch.object(executor, "_run_sprint_validation"):
            result = executor.run("proj-1", sprint)

        assert result.success is True
        executor._workspace.mark_sprint_complete.assert_called_once_with("proj-1", 1)

    def test_test_failure_causes_sprint_failure(self, tmp_path):
        """AC-P2-09: build pass + test.failed > 0 → SprintResult(success=False);
        mark_sprint_complete must NOT be called."""
        from app.shared.dto.sandbox_result import BuildResult, SandboxResult, TestResult
        from app.shared.schemas.file_plan_schema import FilePlan

        mock_sandbox = MagicMock()
        mock_sandbox.run.return_value = SandboxResult(
            project_id="proj-1",
            sprint=1,
            enabled=True,
            install=BuildResult(success=True),
            build=BuildResult(success=True),
            test=TestResult(
                passed=1, failed=2, total=3,
                failures=[
                    {"test_name": "test_login", "error": "AssertionError"},
                    {"test_name": "test_signup", "error": "ValueError"},
                ],
            ),
        )

        executor = self._build_executor(mock_sandbox)
        sprint = self._make_sprint()

        with patch.object(executor, "_load_file_plan", return_value=FilePlan(project_id="proj-1", sprint_number=1)), \
             patch.object(executor, "_run_scrum_master"), \
             patch.object(executor, "_run_sprint_delta"):
            result = executor.run("proj-1", sprint)

        assert result.success is False, "Sprint must fail when tests fail (AC-P2-09)"
        assert "test" in result.message.lower(), (
            f"Failure message should mention tests, got: {result.message!r}"
        )
        executor._workspace.mark_sprint_complete.assert_not_called()

    def test_no_tests_does_not_fail_sprint(self, tmp_path):
        """AC-P2-09: build pass + test.total == 0 (no tests) → sprint can complete.
        Projects that have not yet written tests must not be blocked."""
        from app.shared.dto.sandbox_result import BuildResult, SandboxResult, TestResult
        from app.shared.schemas.file_plan_schema import FilePlan

        mock_sandbox = MagicMock()
        mock_sandbox.run.return_value = SandboxResult(
            project_id="proj-1",
            sprint=1,
            enabled=True,
            install=BuildResult(success=True),
            build=BuildResult(success=True),
            test=TestResult(passed=0, failed=0, total=0),  # no tests found
        )

        executor = self._build_executor(mock_sandbox)
        sprint = self._make_sprint()

        with patch.object(executor, "_load_file_plan", return_value=FilePlan(project_id="proj-1", sprint_number=1)), \
             patch.object(executor, "_run_scrum_master"), \
             patch.object(executor, "_run_sprint_delta"), \
             patch.object(executor, "_run_sprint_deploy_and_review"), \
             patch.object(executor, "_run_sprint_validation"):
            result = executor.run("proj-1", sprint)

        assert result.success is True, (
            "Sprint must not fail when there are no tests (test.total == 0)"
        )
        executor._workspace.mark_sprint_complete.assert_called_once_with("proj-1", 1)

    def test_no_sandbox_wired_sprint_still_completes(self):
        """AC-11: When code_sandbox=None (backward compat), sprint completes without execution gate."""
        from app.shared.schemas.file_plan_schema import FilePlan

        executor = self._build_executor(sandbox=None)
        sprint = self._make_sprint()

        with patch.object(executor, "_load_file_plan", return_value=FilePlan(project_id="proj-1", sprint_number=1)), \
             patch.object(executor, "_run_scrum_master"), \
             patch.object(executor, "_run_sprint_delta"), \
             patch.object(executor, "_run_sprint_deploy_and_review"), \
             patch.object(executor, "_run_sprint_validation"):
            result = executor.run("proj-1", sprint)

        assert result.success is True
        executor._workspace.mark_sprint_complete.assert_called_once()
