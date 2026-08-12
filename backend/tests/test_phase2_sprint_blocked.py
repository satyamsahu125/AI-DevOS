"""test_phase2_sprint_blocked.py — AC-P2-08 regression tests.

Verifies that PipelineSupervisor._run_sprints() transitions to SPRINT_BLOCKED
when SprintExecutor returns success=False, and that successful sprints are
unaffected.

Running:
    cd backend
    python -m pytest tests/test_phase2_sprint_blocked.py -v
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from app.shared.enums.project_state import ProjectState
from app.shared.models.sprint import Sprint, SprintResult
from app.workflow.pipeline_supervisor import PipelineSupervisor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sprint(number: int = 1) -> Sprint:
    return Sprint(
        sprint_id=f"00000000-0000-0000-0000-00000000000{number}",
        sprint_number=number,
        name=f"Sprint {number}",
        goal="Build MVP",
        features=["login"],
    )


def _make_sprint_plan(*sprint_numbers: int) -> MagicMock:
    plan = MagicMock()
    plan.sprints = [_make_sprint(n) for n in sprint_numbers]
    return plan


def _make_supervisor(sprint_executor=None) -> PipelineSupervisor:
    """Minimal PipelineSupervisor for _run_sprints() tests."""
    workspace = MagicMock()
    workspace.get_state.return_value = ProjectState.SPRINT_IN_PROGRESS
    workspace.load_project_json.return_value = {
        "stages_completed": [],
        "completed_sprints": [],
        "mode": "full",
    }
    workspace.update_state.return_value = None
    workspace.update_project_json.return_value = None
    workspace.set_current_sprint.return_value = None
    workspace.get_sprint_plan.return_value = _make_sprint_plan(1)

    engine = MagicMock()
    sprint_exec = sprint_executor or MagicMock()

    return PipelineSupervisor(
        workspace=workspace,
        engine=engine,
        sprint_executor=sprint_exec,
        settings=None,
        code_sandbox=None,  # no sandbox — avoids syntax_check call
    )


# ---------------------------------------------------------------------------
# AC-P2-08 — sprint failure → SPRINT_BLOCKED
# ---------------------------------------------------------------------------

class TestSprintFailureTransitionsSprINTBlocked:

    def test_sprint_failure_sets_sprint_blocked_state(self):
        """AC-P2-08: SprintExecutor.success=False → project state written as SPRINT_BLOCKED."""
        sprint_exec = MagicMock()
        sprint_exec.run.return_value = SprintResult(
            success=False,
            sprint_complete=False,
            message="Build failed: ImportError",
        )
        supervisor = _make_supervisor(sprint_executor=sprint_exec)

        result = supervisor._run_sprints("proj-1", "build a todo app")

        assert result.success is False
        assert result.state == ProjectState.SPRINT_BLOCKED, (
            f"Expected SPRINT_BLOCKED, got {result.state!r}"
        )
        supervisor.workspace.update_state.assert_called_with(
            "proj-1", ProjectState.SPRINT_BLOCKED,
        )

    def test_sprint_failure_result_state_is_sprint_blocked_not_in_progress(self):
        """The returned PipelineResult.state must be SPRINT_BLOCKED, not SPRINT_IN_PROGRESS."""
        sprint_exec = MagicMock()
        sprint_exec.run.return_value = SprintResult(
            success=False, sprint_complete=False, message="Tests failed: 3/5",
        )
        supervisor = _make_supervisor(sprint_executor=sprint_exec)

        result = supervisor._run_sprints("proj-1", "build a todo app")

        assert result.state is not ProjectState.SPRINT_IN_PROGRESS
        assert result.state == ProjectState.SPRINT_BLOCKED

    def test_sprint_failure_persists_failure_reason(self):
        """Failure reason must be written to project.json so it survives restart."""
        failure_msg = "Build failed: no module named fastapi"
        sprint_exec = MagicMock()
        sprint_exec.run.return_value = SprintResult(
            success=False, sprint_complete=False, message=failure_msg,
        )
        supervisor = _make_supervisor(sprint_executor=sprint_exec)

        supervisor._run_sprints("proj-1", "build a todo app")

        calls = [str(c) for c in supervisor.workspace.update_project_json.call_args_list]
        assert any("sprint_1_failure_reason" in c for c in calls), (
            "Failure reason must be persisted under sprint_N_failure_reason key"
        )
        assert any(failure_msg in c for c in calls), (
            "Failure message content must be persisted"
        )

    def test_sprint_failure_message_propagates_to_pipeline_result(self):
        """The PipelineResult.message must include the sprint failure description."""
        sprint_exec = MagicMock()
        sprint_exec.run.return_value = SprintResult(
            success=False, sprint_complete=False, message="Tests failed: 3/5",
        )
        supervisor = _make_supervisor(sprint_executor=sprint_exec)

        result = supervisor._run_sprints("proj-1", "build a todo app")

        assert "Tests failed" in result.message or "failed" in result.message.lower()

    def test_mark_sprint_complete_not_called_on_failure(self):
        """mark_sprint_complete must not be called when sprint fails."""
        sprint_exec = MagicMock()
        sprint_exec.run.return_value = SprintResult(
            success=False, sprint_complete=False, message="Build failed",
        )
        supervisor = _make_supervisor(sprint_executor=sprint_exec)

        supervisor._run_sprints("proj-1", "build a todo app")

        supervisor.workspace.mark_sprint_complete.assert_not_called()


# ---------------------------------------------------------------------------
# Preserved behavior — successful sprint must not be affected
# ---------------------------------------------------------------------------

class TestSuccessfulSprintPreservesState:

    def test_all_sprints_complete_on_success(self):
        """A passing sprint must advance to ALL_SPRINTS_COMPLETE, not SPRINT_BLOCKED."""
        sprint_exec = MagicMock()
        sprint_exec.run.return_value = SprintResult(
            success=True, sprint_complete=True, message="Sprint completed",
        )
        supervisor = _make_supervisor(sprint_executor=sprint_exec)

        result = supervisor._run_sprints("proj-1", "build a todo app")

        assert result.success is True
        assert result.state == ProjectState.ALL_SPRINTS_COMPLETE
        # SPRINT_BLOCKED must never appear in any update_state call
        blocked_calls = [
            c for c in supervisor.workspace.update_state.call_args_list
            if c == call("proj-1", ProjectState.SPRINT_BLOCKED)
        ]
        assert blocked_calls == [], (
            f"SPRINT_BLOCKED must not be written on success, got: {blocked_calls}"
        )

    def test_multi_sprint_all_pass_reaches_all_sprints_complete(self):
        """Two-sprint plan where both pass must reach ALL_SPRINTS_COMPLETE."""
        sprint_exec = MagicMock()
        sprint_exec.run.return_value = SprintResult(
            success=True, sprint_complete=True, message="Sprint completed",
        )
        supervisor = _make_supervisor(sprint_executor=sprint_exec)
        supervisor.workspace.get_sprint_plan.return_value = _make_sprint_plan(1, 2)

        result = supervisor._run_sprints("proj-1", "build a todo app")

        assert result.success is True
        assert result.state == ProjectState.ALL_SPRINTS_COMPLETE
        assert sprint_exec.run.call_count == 2

    def test_second_sprint_fails_sets_sprint_blocked(self):
        """Two-sprint plan where sprint 2 fails → SPRINT_BLOCKED after sprint 1 completes."""
        call_count = {"n": 0}

        def _sprint_run(project_id, sprint):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return SprintResult(success=True, sprint_complete=True)
            return SprintResult(
                success=False, sprint_complete=False, message="Sprint 2 build failed",
            )

        sprint_exec = MagicMock()
        sprint_exec.run.side_effect = _sprint_run
        supervisor = _make_supervisor(sprint_executor=sprint_exec)
        supervisor.workspace.get_sprint_plan.return_value = _make_sprint_plan(1, 2)

        result = supervisor._run_sprints("proj-1", "build a todo app")

        assert result.success is False
        assert result.state == ProjectState.SPRINT_BLOCKED
        supervisor.workspace.update_state.assert_called_with(
            "proj-1", ProjectState.SPRINT_BLOCKED,
        )
