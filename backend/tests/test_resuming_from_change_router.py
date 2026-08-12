"""test_resuming_from_change_router.py — State router: RESUMING_FROM_CHANGE → REPLANNING.

Verifies that PipelineSupervisor._run_impl() recognises RESUMING_FROM_CHANGE
and transitions to REPLANNING without executing any agents or reaching a
terminal success/failure state.

Running:
    cd backend
    python -m pytest tests/test_resuming_from_change_router.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from app.shared.enums.project_state import ProjectState
from app.workflow.pipeline_supervisor import PipelineSupervisor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_supervisor(state: ProjectState) -> tuple[PipelineSupervisor, MagicMock]:
    """Return (supervisor, workspace_mock) pre-configured with the given state."""
    workspace = MagicMock()
    workspace.get_state.return_value = state
    workspace.load_project_json.return_value = {
        "stages_completed": ["StrategicReview"],
        "mode": "full",
    }
    workspace.update_state.return_value = None

    engine = MagicMock()
    sprint_executor = MagicMock()

    supervisor = PipelineSupervisor(
        workspace=workspace,
        engine=engine,
        sprint_executor=sprint_executor,
        settings=None,
        code_sandbox=None,
    )
    return supervisor, workspace


# ---------------------------------------------------------------------------
# Core routing tests
# ---------------------------------------------------------------------------

class TestResumingFromChangeRouter:

    def test_resuming_from_change_is_recognized(self):
        """RESUMING_FROM_CHANGE must not fall through to the terminal-state handler."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        result = supervisor._run_impl("proj-1", "build a todo app")
        # Not a silent unknown-state failure
        assert "Pipeline in state" not in result.message

    def test_transitions_to_replanning(self):
        """The state must be updated to REPLANNING."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        supervisor._run_impl("proj-1", "build a todo app")
        workspace.update_state.assert_called_with("proj-1", ProjectState.REPLANNING)

    def test_returned_state_is_replanning(self):
        """PipelineResult.state must be REPLANNING."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        result = supervisor._run_impl("proj-1", "build a todo app")
        assert result.state == ProjectState.REPLANNING

    def test_returns_success_true(self):
        """The transition itself is successful — not a failure."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        result = supervisor._run_impl("proj-1", "build a todo app")
        assert result.success is True

    def test_does_not_become_deployable(self):
        """RESUMING_FROM_CHANGE must never reach DEPLOYABLE."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        result = supervisor._run_impl("proj-1", "build a todo app")
        assert result.state != ProjectState.DEPLOYABLE
        deployable_calls = [
            c for c in workspace.update_state.call_args_list
            if c == call("proj-1", ProjectState.DEPLOYABLE)
        ]
        assert deployable_calls == []

    def test_does_not_become_done(self):
        """RESUMING_FROM_CHANGE must never reach DONE."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        result = supervisor._run_impl("proj-1", "build a todo app")
        assert result.state != ProjectState.DONE

    def test_no_agents_executed(self):
        """No stage engine calls must be made during this transition."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        supervisor._run_impl("proj-1", "build a todo app")
        supervisor.engine.run.assert_not_called()

    def test_sprint_executor_not_called(self):
        """Sprint executor must not be invoked during this transition."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        supervisor._run_impl("proj-1", "build a todo app")
        supervisor._sprint_executor.run.assert_not_called()

    def test_stages_completed_preserved_in_result(self):
        """Existing stages_completed must be included in the returned result."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        result = supervisor._run_impl("proj-1", "build a todo app")
        assert "StrategicReview" in result.completed_stages

    def test_message_describes_replanning(self):
        """The result message must describe the replanning intent."""
        supervisor, workspace = _make_supervisor(ProjectState.RESUMING_FROM_CHANGE)
        result = supervisor._run_impl("proj-1", "build a todo app")
        assert "replan" in result.message.lower() or "change" in result.message.lower()


# ---------------------------------------------------------------------------
# Existing state-machine behavior must be unchanged
# ---------------------------------------------------------------------------

class TestExistingStateRoutingUnaffected:

    def test_discovery_state_still_routes_to_discovery(self):
        """REQUIREMENTS_READY must route to _run_discovery, never to the RESUMING handler."""
        supervisor, workspace = _make_supervisor(ProjectState.REQUIREMENTS_READY)
        # engine.run returns a MagicMock; _run_discovery completes without RESUMING handler
        result = supervisor._run_impl("proj-1", "build something")
        # The key assertion: REPLANNING must never be written for a non-resuming state
        replanning_calls = [
            c for c in workspace.update_state.call_args_list
            if c == call("proj-1", ProjectState.REPLANNING)
        ]
        assert replanning_calls == [], (
            "REPLANNING must not be written when starting from a discovery state"
        )

    def test_sprint_in_progress_does_not_trigger_resuming_handler(self):
        """SPRINT_IN_PROGRESS must not be misrouted to the RESUMING_FROM_CHANGE handler."""
        supervisor, workspace = _make_supervisor(ProjectState.SPRINT_IN_PROGRESS)
        workspace.get_sprint_plan.return_value = MagicMock(sprints=[])
        result = supervisor._run_impl("proj-1", "build something")
        replanning_calls = [
            c for c in workspace.update_state.call_args_list
            if c == call("proj-1", ProjectState.REPLANNING)
        ]
        assert replanning_calls == [], (
            "REPLANNING must not be written for SPRINT_IN_PROGRESS"
        )

    def test_deployable_still_returns_success_from_terminal_handler(self):
        """DEPLOYABLE must still reach the terminal-state handler and return success."""
        supervisor, workspace = _make_supervisor(ProjectState.DEPLOYABLE)
        result = supervisor._run_impl("proj-1", "build something")
        assert result.success is True
        assert result.state == ProjectState.DEPLOYABLE
