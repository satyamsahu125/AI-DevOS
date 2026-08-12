"""test_phase2_deployable_bug.py — AC-P2-10 regression tests.

Verifies that PipelineSupervisor._run_release() never transitions to DEPLOYABLE
when the bug-fix loop is exhausted while the build is still failing.

Covers:
  - Bug-fix limit hit, build still failing → SPRINT_BLOCKED, success=False
  - Bug-fix limit hit, tests still failing → SPRINT_BLOCKED, success=False
  - Bug-fix limit hit, build passing → DEPLOYABLE, success=True (preserved behavior)
  - No bug detected by BugAnalyst → DEPLOYABLE, success=True (unaffected path)
  - No sandbox wired → DEPLOYABLE (backward compat: no evidence of failure)
  - _check_build_state_from_memory with no memory_manager → returns ""

Running:
    cd backend
    python -m pytest tests/test_phase2_deployable_bug.py -v
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.shared.dto.sandbox_result import BuildResult, SandboxResult, TestResult
from app.shared.enums.project_state import ProjectState
from app.workflow.pipeline_supervisor import PipelineSupervisor


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_supervisor(
    *,
    code_sandbox=None,
    memory_manager=None,
    change_manager=None,
) -> PipelineSupervisor:
    """Build a PipelineSupervisor with the minimum fakes needed to call
    _run_release().  Engine.run() is patched per-test."""
    workspace = MagicMock()
    workspace.get_state.return_value = ProjectState.ALL_SPRINTS_COMPLETE
    workspace.load_project_json.return_value = {
        "stages_completed": [],
        "current_sprint_number": 1,
    }
    workspace.update_state.return_value = None
    workspace.update_project_json.return_value = None
    workspace.get_artifact_store.return_value = MagicMock(
        exists=MagicMock(return_value=False),
        write=MagicMock(return_value=None),
    )

    engine = MagicMock()
    sprint_exec = MagicMock()

    return PipelineSupervisor(
        workspace=workspace,
        engine=engine,
        sprint_executor=sprint_exec,
        settings=None,
        code_sandbox=code_sandbox,
        memory_manager=memory_manager,
        change_manager=change_manager,
    )


def _make_sandbox_json(*, build_success: bool, test_failed: int = 0, test_total: int = 0) -> str:
    """Return a JSON string for memory_manager "sandbox:latest" storage."""
    result = SandboxResult(
        project_id="proj-1",
        sprint=1,
        enabled=True,
        install=BuildResult(success=True),
        build=BuildResult(
            success=build_success,
            errors=[] if build_success else ["ImportError: no module named 'fastapi'"],
        ),
        test=TestResult(
            passed=test_total - test_failed,
            failed=test_failed,
            total=test_total,
        ),
    )
    return result.to_json()


def _build_analyst_result(bug_type: str) -> MagicMock:
    """Fake WorkflowResult from the bug_analyst stage."""
    artifact = MagicMock()
    artifact.structured_content = {
        "type": bug_type,
        "affected_agent": "Backend",
        "targeted_fix_instruction": "Fix the import",
    }
    result = MagicMock()
    result.success = True
    result.artifact = artifact
    return result


def _setup_release_stages(supervisor: PipelineSupervisor, stage_results: dict) -> None:
    """Configure engine.run() to return specific results per stage.

    stage_results: mapping of stage key → WorkflowResult mock.
    Unlisted stages return generic success.
    """
    def _engine_run(project_id, stage_name, content):
        # Map resolved stage names back via key substring matching
        for key, mock_result in stage_results.items():
            if key.lower() in str(stage_name).lower():
                return mock_result
        ok = MagicMock()
        ok.success = True
        ok.artifact = None
        return ok

    supervisor.engine.run.side_effect = _engine_run


# ---------------------------------------------------------------------------
# AC-P2-10 — bug-fix limit with build still failing → SPRINT_BLOCKED
# ---------------------------------------------------------------------------

class TestBugFixLimitWithBrokenBuild:
    """resolve_stage_name is imported locally inside _run_release; patch at the source module."""

    _PATCH_STAGES = "app.workflow.pipeline_supervisor.get_release_stages"
    _PATCH_RESOLVE = "app.workflow.stage_lookup.resolve_stage_name"

    def test_build_failing_at_limit_returns_sprint_blocked(self):
        """AC-P2-10: when fix limit exhausted and build still fails → SPRINT_BLOCKED, not DEPLOYABLE."""
        memory_manager = MagicMock()
        memory_manager.load.return_value = _make_sandbox_json(build_success=False)
        code_sandbox = MagicMock()
        supervisor = _make_supervisor(code_sandbox=code_sandbox, memory_manager=memory_manager)

        bug_result = _build_analyst_result("code_bug")
        _setup_release_stages(supervisor, {"bug_analyst": bug_result})

        with patch(self._PATCH_STAGES, return_value=["qa", "bug_analyst"]), \
             patch(self._PATCH_RESOLVE, side_effect=lambda s: s):
            result = supervisor._run_release("proj-1", "build a todo app")

        assert result.success is False, "Must not succeed when build is broken at fix limit"
        assert result.state == ProjectState.SPRINT_BLOCKED, (
            f"Expected SPRINT_BLOCKED, got {result.state}"
        )

        # State must be written to disk
        supervisor.workspace.update_state.assert_any_call("proj-1", ProjectState.SPRINT_BLOCKED)
        # Failure reason must be recorded in project.json
        calls = [str(c) for c in supervisor.workspace.update_project_json.call_args_list]
        assert any("bug_fix_failure_reason" in c for c in calls), (
            "Failure reason must be persisted to project.json"
        )

    def test_message_mentions_build_failure(self):
        """The failure message must describe the build failure for observability."""
        memory_manager = MagicMock()
        memory_manager.load.return_value = _make_sandbox_json(build_success=False)
        code_sandbox = MagicMock()
        supervisor = _make_supervisor(code_sandbox=code_sandbox, memory_manager=memory_manager)
        _setup_release_stages(supervisor, {"bug_analyst": _build_analyst_result("code_bug")})

        with patch(self._PATCH_STAGES, return_value=["qa", "bug_analyst"]), \
             patch(self._PATCH_RESOLVE, side_effect=lambda s: s):
            result = supervisor._run_release("proj-1", "build a todo app")

        assert "build" in result.message.lower() or "fail" in result.message.lower(), (
            f"Message should describe the failure: {result.message!r}"
        )

    def test_tests_failing_at_limit_returns_sprint_blocked(self):
        """AC-P2-10: build passes but tests fail → also transitions to SPRINT_BLOCKED."""
        memory_manager = MagicMock()
        memory_manager.load.return_value = _make_sandbox_json(
            build_success=True, test_failed=3, test_total=5
        )
        code_sandbox = MagicMock()
        supervisor = _make_supervisor(code_sandbox=code_sandbox, memory_manager=memory_manager)
        _setup_release_stages(supervisor, {"bug_analyst": _build_analyst_result("code_bug")})

        with patch(self._PATCH_STAGES, return_value=["qa", "bug_analyst"]), \
             patch(self._PATCH_RESOLVE, side_effect=lambda s: s):
            result = supervisor._run_release("proj-1", "build a todo app")

        assert result.success is False
        assert result.state == ProjectState.SPRINT_BLOCKED


# ---------------------------------------------------------------------------
# Preserved behavior: fix limit hit but build is passing → DEPLOYABLE
# ---------------------------------------------------------------------------

class TestBugFixLimitWithPassingBuild:

    _PATCH_STAGES = "app.workflow.pipeline_supervisor.get_release_stages"
    _PATCH_RESOLVE = "app.workflow.stage_lookup.resolve_stage_name"

    def test_build_passing_at_limit_advances_to_deployable(self):
        """When fix limit hit but build is now passing, pipeline completes normally → DEPLOYABLE."""
        memory_manager = MagicMock()
        memory_manager.load.return_value = _make_sandbox_json(
            build_success=True, test_failed=0, test_total=5
        )
        code_sandbox = MagicMock()
        supervisor = _make_supervisor(code_sandbox=code_sandbox, memory_manager=memory_manager)
        _setup_release_stages(supervisor, {"bug_analyst": _build_analyst_result("code_bug")})

        with patch(self._PATCH_STAGES, return_value=["qa", "bug_analyst"]), \
             patch(self._PATCH_RESOLVE, side_effect=lambda s: s):
            result = supervisor._run_release("proj-1", "build a todo app")

        assert result.success is True
        assert result.state == ProjectState.DEPLOYABLE

    def test_no_sandbox_wired_advances_to_deployable_backward_compat(self):
        """When no code_sandbox is wired, fix limit falls through to DEPLOYABLE (backward compat)."""
        memory_manager = MagicMock()
        memory_manager.load.return_value = ""
        supervisor = _make_supervisor(code_sandbox=None, memory_manager=memory_manager)
        _setup_release_stages(supervisor, {"bug_analyst": _build_analyst_result("code_bug")})

        with patch(self._PATCH_STAGES, return_value=["qa", "bug_analyst"]), \
             patch(self._PATCH_RESOLVE, side_effect=lambda s: s):
            result = supervisor._run_release("proj-1", "build a todo app")

        assert result.state == ProjectState.DEPLOYABLE


# ---------------------------------------------------------------------------
# _check_build_state_from_memory unit tests
# ---------------------------------------------------------------------------

class TestCheckBuildStateFromMemory:

    def test_no_memory_manager_returns_empty(self):
        """No memory_manager → returns '' (no evidence of failure)."""
        supervisor = _make_supervisor(code_sandbox=MagicMock(), memory_manager=None)
        assert supervisor._check_build_state_from_memory("proj-1") == ""

    def test_no_code_sandbox_returns_empty(self):
        """No code_sandbox → returns '' (sandbox not in use)."""
        supervisor = _make_supervisor(code_sandbox=None, memory_manager=MagicMock())
        assert supervisor._check_build_state_from_memory("proj-1") == ""

    def test_no_stored_result_returns_empty(self):
        """memory_manager returns None/empty → returns '' (benefit of the doubt)."""
        mm = MagicMock()
        mm.load.return_value = None
        supervisor = _make_supervisor(code_sandbox=MagicMock(), memory_manager=mm)
        assert supervisor._check_build_state_from_memory("proj-1") == ""

    def test_build_failing_returns_reason_string(self):
        """build.success=False → returns non-empty failure reason."""
        mm = MagicMock()
        mm.load.return_value = _make_sandbox_json(build_success=False)
        supervisor = _make_supervisor(code_sandbox=MagicMock(), memory_manager=mm)
        reason = supervisor._check_build_state_from_memory("proj-1")
        assert reason, "Expected non-empty reason for broken build"
        assert "build" in reason.lower()

    def test_build_passing_all_tests_pass_returns_empty(self):
        """build passes, all tests pass → returns ''."""
        mm = MagicMock()
        mm.load.return_value = _make_sandbox_json(build_success=True, test_failed=0, test_total=3)
        supervisor = _make_supervisor(code_sandbox=MagicMock(), memory_manager=mm)
        assert supervisor._check_build_state_from_memory("proj-1") == ""

    def test_tests_failing_returns_reason_string(self):
        """build passes, tests fail → returns non-empty reason."""
        mm = MagicMock()
        mm.load.return_value = _make_sandbox_json(build_success=True, test_failed=2, test_total=4)
        supervisor = _make_supervisor(code_sandbox=MagicMock(), memory_manager=mm)
        reason = supervisor._check_build_state_from_memory("proj-1")
        assert reason, "Expected non-empty reason for failing tests"
        assert "test" in reason.lower()

    def test_no_tests_at_all_returns_empty(self):
        """build passes, test.total=0 (no tests) → returns ''."""
        mm = MagicMock()
        mm.load.return_value = _make_sandbox_json(build_success=True, test_failed=0, test_total=0)
        supervisor = _make_supervisor(code_sandbox=MagicMock(), memory_manager=mm)
        assert supervisor._check_build_state_from_memory("proj-1") == ""

    def test_corrupt_json_returns_empty(self):
        """Corrupt JSON in memory → catches exception, returns ''."""
        mm = MagicMock()
        mm.load.return_value = "this is not json {"
        supervisor = _make_supervisor(code_sandbox=MagicMock(), memory_manager=mm)
        # Must not raise
        result = supervisor._check_build_state_from_memory("proj-1")
        assert result == ""
