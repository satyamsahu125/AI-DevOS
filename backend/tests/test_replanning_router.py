"""test_replanning_router.py — REPLANNING state router in PipelineSupervisor.

Verifies that _run_impl() correctly dispatches from REPLANNING to the right
pipeline phase based on the stages_completed / sprint plan already in project.json
(set by ChangeManager.apply()).

Key design:
  - Phase methods (_run_discovery, _run_sprints, _run_release) are patched so
    tests prove routing decisions, not phase-execution correctness.
  - workspace.update_state call_args tell us which phase entry state was chosen.

Running:
    cd backend
    python -m pytest tests/test_replanning_router.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from app.shared.dto.pipeline_result import PipelineResult
from app.shared.enums.project_state import ProjectState
from app.shared.models.sprint import Sprint, SprintPlan, SprintStatus
from app.workflow.pipeline_supervisor import PipelineSupervisor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sprint(number: int, status: SprintStatus = SprintStatus.PLANNED) -> Sprint:
    return Sprint(
        sprint_id=f"0000000{number}",
        sprint_number=number,
        name=f"Sprint {number}",
        goal=f"Goal {number}",
        status=status,
    )


def _plan(sprints: list[Sprint], stale: bool = False) -> SprintPlan:
    return SprintPlan(
        project_id="proj-1",
        total_sprints=len(sprints),
        sprints=sprints,
        stale=stale,
    )


def _success_result(**kw) -> PipelineResult:
    defaults = dict(
        project_id="proj-1",
        state=ProjectState.DESIGN_APPROVED,
        success=True,
        message="ok",
        completed_stages=[],
    )
    return PipelineResult(**{**defaults, **kw})


def _make_supervisor(
    stages_completed: list[str],
    completed_sprints: list[int] | None = None,
    sprint_plan: SprintPlan | None = None,
    mode: str = "full",
) -> tuple[PipelineSupervisor, MagicMock]:
    """Return (supervisor, workspace) with REPLANNING as initial state."""
    workspace = MagicMock()
    workspace.get_state.return_value = ProjectState.REPLANNING
    workspace.load_project_json.return_value = {
        "stages_completed": stages_completed,
        "completed_sprints": completed_sprints or [],
        "mode": mode,
    }
    workspace.get_sprint_plan.return_value = sprint_plan
    workspace.update_state.return_value = None

    supervisor = PipelineSupervisor(
        workspace=workspace,
        engine=MagicMock(),
        sprint_executor=MagicMock(),
        settings=None,
        code_sandbox=None,
    )
    return supervisor, workspace


def _all_discovery_stages() -> list[str]:
    """Return the CamelCase stage names that populate stages_completed for full discovery."""
    from app.workflow.pipeline_supervisor import get_discovery_stages
    from app.workflow.stage_lookup import resolve_stage_name
    return [resolve_stage_name(s) for s in get_discovery_stages()]


# ---------------------------------------------------------------------------
# REPLANNING → Discovery phase
# ---------------------------------------------------------------------------

class TestReplanningToDiscovery:

    def _run_with_discovery_patched(
        self,
        stages_completed: list[str],
        sprint_plan: SprintPlan | None = None,
    ) -> tuple[PipelineResult, MagicMock]:
        supervisor, workspace = _make_supervisor(
            stages_completed=stages_completed,
            sprint_plan=sprint_plan,
        )
        disc_result = _success_result(state=ProjectState.DESIGN_APPROVED)
        sprint_result = _success_result(state=ProjectState.ALL_SPRINTS_COMPLETE)
        release_result = _success_result(state=ProjectState.DEPLOYABLE)

        with (
            patch.object(supervisor, "_run_discovery", return_value=disc_result) as mock_disc,
            patch.object(supervisor, "_run_sprints", return_value=sprint_result),
            patch.object(supervisor, "_run_release", return_value=release_result),
        ):
            # get_state is called 3× in the Discovery → Sprints → Release path:
            #   call 1: initial state check
            #   call 2: after _run_discovery returns (gate check)
            #   call 3: after _run_sprints returns (release phase check)
            workspace.get_state.side_effect = [
                ProjectState.REPLANNING,           # initial
                ProjectState.DESIGN_APPROVED,      # after discovery
                ProjectState.ALL_SPRINTS_COMPLETE, # after sprints
            ]
            result = supervisor._run_impl("proj-1", "build a todo app")
        return result, workspace, mock_disc

    def test_missing_discovery_stage_routes_to_discovery(self):
        """When any discovery stage is absent, REPLANNING must enter Discovery."""
        # Only StrategicReview completed — everything else missing
        _, workspace, mock_disc = self._run_with_discovery_patched(
            stages_completed=["StrategicReview"],
        )
        mock_disc.assert_called_once_with("proj-1", "build a todo app")

    def test_state_set_to_requirements_ready_before_discovery(self):
        """update_state(REQUIREMENTS_READY) must be called before _run_discovery."""
        _, workspace, _ = self._run_with_discovery_patched(
            stages_completed=["StrategicReview"],
        )
        # First update_state call must be REQUIREMENTS_READY
        first_state_update = workspace.update_state.call_args_list[0]
        assert first_state_update == call("proj-1", ProjectState.REQUIREMENTS_READY)

    def test_empty_stages_completed_routes_to_discovery(self):
        """Completely empty stages_completed must enter Discovery, not Sprints/Release."""
        _, workspace, mock_disc = self._run_with_discovery_patched(
            stages_completed=[],
        )
        mock_disc.assert_called_once()

    def test_completed_discovery_stages_not_passed_to_phase_again(self):
        """Stages already in stages_completed must not cause extra calls; routing only."""
        # StrategicReview is safe — only ProductOwner and below are missing
        _, workspace, mock_disc = self._run_with_discovery_patched(
            stages_completed=["StrategicReview"],
        )
        # _run_discovery is called once (the patched version handles skipping internally)
        assert mock_disc.call_count == 1


# ---------------------------------------------------------------------------
# REPLANNING → Sprints phase
# ---------------------------------------------------------------------------

class TestReplanningToSprints:

    def _run_with_sprints_patched(
        self,
        stages_completed: list[str],
        sprint_plan: SprintPlan | None = None,
        completed_sprints: list[int] | None = None,
    ) -> tuple[PipelineResult, MagicMock, MagicMock]:
        supervisor, workspace = _make_supervisor(
            stages_completed=stages_completed,
            sprint_plan=sprint_plan,
            completed_sprints=completed_sprints or [],
        )
        sprint_result = _success_result(state=ProjectState.ALL_SPRINTS_COMPLETE)
        release_result = _success_result(state=ProjectState.DEPLOYABLE)

        with (
            patch.object(supervisor, "_run_sprints", return_value=sprint_result) as mock_sprint,
            patch.object(supervisor, "_run_release", return_value=release_result),
        ):
            workspace.get_state.side_effect = [
                ProjectState.REPLANNING,
                ProjectState.ALL_SPRINTS_COMPLETE,
            ]
            result = supervisor._run_impl("proj-1", "build a todo app")
        return result, workspace, mock_sprint

    def test_stale_sprint_plan_routes_to_sprints(self):
        """sprint_plan.stale=True with discovery complete must enter Sprints phase."""
        all_disc = _all_discovery_stages()
        plan = _plan([_sprint(1, SprintStatus.COMPLETE)], stale=True)
        _, workspace, mock_sprint = self._run_with_sprints_patched(
            stages_completed=all_disc,
            sprint_plan=plan,
            completed_sprints=[1],
        )
        mock_sprint.assert_called_once_with("proj-1", "build a todo app")

    def test_pending_sprint_routes_to_sprints(self):
        """A sprint not in completed_sprints (still planned) must enter Sprints phase."""
        all_disc = _all_discovery_stages()
        plan = _plan([_sprint(1, SprintStatus.COMPLETE), _sprint(2, SprintStatus.PLANNED)])
        _, workspace, mock_sprint = self._run_with_sprints_patched(
            stages_completed=all_disc,
            sprint_plan=plan,
            completed_sprints=[1],  # Sprint 2 is pending
        )
        mock_sprint.assert_called_once()

    def test_state_set_to_sprint_in_progress_before_sprints(self):
        """update_state(SPRINT_IN_PROGRESS) must precede _run_sprints call."""
        all_disc = _all_discovery_stages()
        plan = _plan([_sprint(1, SprintStatus.PLANNED)])
        _, workspace, _ = self._run_with_sprints_patched(
            stages_completed=all_disc,
            sprint_plan=plan,
            completed_sprints=[],
        )
        first_update = workspace.update_state.call_args_list[0]
        assert first_update == call("proj-1", ProjectState.SPRINT_IN_PROGRESS)

    def test_discovery_not_called_when_sprints_resume(self):
        """_run_discovery must NOT be called when routing goes to Sprints."""
        all_disc = _all_discovery_stages()
        plan = _plan([_sprint(1, SprintStatus.PLANNED)], stale=True)
        supervisor, workspace = _make_supervisor(
            stages_completed=all_disc,
            sprint_plan=plan,
            completed_sprints=[],
        )
        sprint_result = _success_result(state=ProjectState.ALL_SPRINTS_COMPLETE)
        with (
            patch.object(supervisor, "_run_discovery") as mock_disc,
            patch.object(supervisor, "_run_sprints", return_value=sprint_result),
            patch.object(supervisor, "_run_release", return_value=_success_result(state=ProjectState.DEPLOYABLE)),
        ):
            workspace.get_state.side_effect = [
                ProjectState.REPLANNING,
                ProjectState.ALL_SPRINTS_COMPLETE,
            ]
            supervisor._run_impl("proj-1", "build a todo app")
        mock_disc.assert_not_called()


# ---------------------------------------------------------------------------
# REPLANNING → Release phase
# ---------------------------------------------------------------------------

class TestReplanningToRelease:

    def test_all_stages_and_sprints_done_routes_to_release(self):
        """When discovery is complete and all sprints are done, enter Release."""
        all_disc = _all_discovery_stages()
        plan = _plan([_sprint(1, SprintStatus.COMPLETE), _sprint(2, SprintStatus.COMPLETE)])
        supervisor, workspace = _make_supervisor(
            stages_completed=all_disc,
            sprint_plan=plan,
            completed_sprints=[1, 2],
        )
        release_result = _success_result(state=ProjectState.DEPLOYABLE)
        with (
            patch.object(supervisor, "_run_discovery") as mock_disc,
            patch.object(supervisor, "_run_sprints") as mock_sprint,
            patch.object(supervisor, "_run_release", return_value=release_result) as mock_rel,
        ):
            workspace.get_state.return_value = ProjectState.REPLANNING
            supervisor._run_impl("proj-1", "build a todo app")

        mock_disc.assert_not_called()
        mock_sprint.assert_not_called()
        mock_rel.assert_called_once()

    def test_state_set_to_all_sprints_complete_before_release(self):
        """update_state(ALL_SPRINTS_COMPLETE) must precede _run_release."""
        all_disc = _all_discovery_stages()
        plan = _plan([_sprint(1, SprintStatus.COMPLETE)])
        supervisor, workspace = _make_supervisor(
            stages_completed=all_disc,
            sprint_plan=plan,
            completed_sprints=[1],
        )
        with (
            patch.object(supervisor, "_run_release", return_value=_success_result(state=ProjectState.DEPLOYABLE)),
        ):
            workspace.get_state.return_value = ProjectState.REPLANNING
            supervisor._run_impl("proj-1", "build a todo app")

        first_update = workspace.update_state.call_args_list[0]
        assert first_update == call("proj-1", ProjectState.ALL_SPRINTS_COMPLETE)

    def test_no_sprint_plan_no_pending_sprints_routes_to_release(self):
        """No sprint plan means no pending sprints — route to Release."""
        all_disc = _all_discovery_stages()
        supervisor, workspace = _make_supervisor(
            stages_completed=all_disc,
            sprint_plan=None,  # sprint planner may not have generated a plan yet
        )
        with (
            patch.object(supervisor, "_run_release", return_value=_success_result(state=ProjectState.DEPLOYABLE)) as mock_rel,
            patch.object(supervisor, "_run_sprints") as mock_sprint,
            patch.object(supervisor, "_run_discovery") as mock_disc,
        ):
            workspace.get_state.return_value = ProjectState.REPLANNING
            supervisor._run_impl("proj-1", "build a todo app")

        mock_disc.assert_not_called()
        mock_sprint.assert_not_called()
        mock_rel.assert_called_once()


# ---------------------------------------------------------------------------
# Guard: unaffected stages not re-executed
# ---------------------------------------------------------------------------

class TestUnaffectedStagesPreserved:

    def test_safe_stages_still_in_stages_completed(self):
        """stages_completed content is passed through to phase methods unchanged."""
        safe = ["StrategicReview", "ProductOwner"]
        plan = _plan([_sprint(1, SprintStatus.PLANNED)])
        all_disc = _all_discovery_stages()

        supervisor, workspace = _make_supervisor(
            stages_completed=safe,   # only safe stages remain
            sprint_plan=plan,
            completed_sprints=[],
        )
        # Stub discovery — since safe stages are a subset, discovery is incomplete
        disc_result = _success_result(state=ProjectState.DESIGN_APPROVED)
        sprint_result = _success_result(state=ProjectState.ALL_SPRINTS_COMPLETE)
        captured_pj: list[dict] = []

        original_load = workspace.load_project_json.return_value

        def _capture_and_return(pid):
            captured_pj.append(dict(original_load))
            return dict(original_load)

        workspace.load_project_json.side_effect = _capture_and_return

        with (
            patch.object(supervisor, "_run_discovery", return_value=disc_result),
            patch.object(supervisor, "_run_sprints", return_value=sprint_result),
            patch.object(supervisor, "_run_release", return_value=_success_result(state=ProjectState.DEPLOYABLE)),
        ):
            workspace.get_state.side_effect = [
                ProjectState.REPLANNING,
                ProjectState.DESIGN_APPROVED,
                ProjectState.ALL_SPRINTS_COMPLETE,
            ]
            supervisor._run_impl("proj-1", "build a todo app")

        # The REPLANNING handler must not have modified the stages_completed list
        # that was loaded from project.json — safe stages must remain intact.
        assert captured_pj, "load_project_json must have been called"
        first_load = captured_pj[0]
        assert first_load["stages_completed"] == safe


# ---------------------------------------------------------------------------
# Guard: existing state routing unaffected
# ---------------------------------------------------------------------------

class TestExistingRoutingUnchanged:

    def test_resuming_from_change_still_transitions_to_replanning(self):
        """The RESUMING_FROM_CHANGE → REPLANNING router must still work."""
        workspace = MagicMock()
        workspace.get_state.return_value = ProjectState.RESUMING_FROM_CHANGE
        workspace.load_project_json.return_value = {
            "stages_completed": ["StrategicReview"],
            "mode": "full",
        }
        supervisor = PipelineSupervisor(
            workspace=workspace,
            engine=MagicMock(),
            sprint_executor=MagicMock(),
            settings=None,
            code_sandbox=None,
        )
        result = supervisor._run_impl("proj-1", "build a todo app")
        assert result.state == ProjectState.REPLANNING
        assert result.success is True
        workspace.update_state.assert_called_with("proj-1", ProjectState.REPLANNING)

    def test_deployable_terminal_state_unaffected(self):
        """DEPLOYABLE must still return success without hitting REPLANNING handler."""
        workspace = MagicMock()
        workspace.get_state.return_value = ProjectState.DEPLOYABLE
        workspace.load_project_json.return_value = {"stages_completed": [], "mode": "full"}
        supervisor = PipelineSupervisor(
            workspace=workspace,
            engine=MagicMock(),
            sprint_executor=MagicMock(),
            settings=None,
            code_sandbox=None,
        )
        result = supervisor._run_impl("proj-1", "build")
        assert result.success is True
        assert result.state == ProjectState.DEPLOYABLE
        # update_state must NOT have been called with REQUIREMENTS_READY etc.
        for c in workspace.update_state.call_args_list:
            assert c != call("proj-1", ProjectState.REQUIREMENTS_READY)
            assert c != call("proj-1", ProjectState.SPRINT_IN_PROGRESS)
