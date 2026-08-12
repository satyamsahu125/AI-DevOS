"""test_phase4_sprint_plan_gate.py — Phase 4 sprint plan review gate.

Verifies:
  1. After sprint_planner stage completes (non-quick mode), pipeline pauses at
     SPRINT_PLAN_REVIEW_PENDING and returns requires_user_action=True.
  2. The state transition to SPRINT_PLAN_REVIEW_PENDING is written to workspace.
  3. In quick mode, the sprint_planner gate is skipped (no pause).
  4. The architect gate still works correctly (non-regression).
  5. The designer gate still works correctly (non-regression).
  6. manager._await_gate("sprint_plan") returns requires_user_action=True.
  7. manager.run() delegates to _await_gate when state is SPRINT_PLAN_REVIEW_PENDING.
  8. _run_sprints() respects the SPRINT_PLAN_REVIEW_PENDING state (existing defence,
     confirmed still non-dead).
  9. gates.py _assert_gate_state raises HTTP 409 for wrong state.
 10. GateResult.to_dict() includes all required keys.

Running:
    cd backend
    python -m pytest tests/test_phase4_sprint_plan_gate.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call
import pytest

from app.shared.enums.project_state import ProjectState
from app.shared.dto.pipeline_result import PipelineResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_supervisor(quick_mode: bool = False):
    """Return a PipelineSupervisor with all heavy deps mocked out."""
    from app.workflow.pipeline_supervisor import PipelineSupervisor

    workspace = MagicMock()
    workspace.get_workspace_path.return_value = "/tmp/proj"
    workspace.get_state.return_value = ProjectState.REQUIREMENTS_READY
    workspace.load_project_json.return_value = {"stages_completed": [], "completed_sprints": []}
    workspace.update_state = MagicMock()
    workspace.update_project_json = MagicMock()
    workspace.get_sprint_plan.return_value = None

    engine = MagicMock()
    sprint_executor = MagicMock()
    settings = MagicMock()

    sup = PipelineSupervisor(
        workspace=workspace,
        engine=engine,
        sprint_executor=sprint_executor,
        settings=settings,
    )

    # Stub _get_project_mode to return "quick" or "normal"
    sup._get_project_mode = MagicMock(return_value="quick" if quick_mode else "normal")

    return sup, workspace


# ---------------------------------------------------------------------------
# 1-2: Sprint plan gate pauses pipeline (non-quick mode)
# ---------------------------------------------------------------------------

class TestSprintPlanGateNonQuick:

    def _run_discovery_to_sprint_planner(self):
        """Run _run_discovery() up to sprint_planner, mocking each stage success."""
        sup, workspace = _make_supervisor(quick_mode=False)

        # Patch get_discovery_stages to return only sprint_planner (simplest path)
        with patch("app.workflow.pipeline_supervisor.get_discovery_stages",
                   return_value=["sprint_planner"]):
            # Patch resolve_stage_name
            with patch("app.workflow.stage_lookup.resolve_stage_name",
                       return_value="SprintPlanning"):
                # Patch _run_stage_safe to return success
                sup._run_stage_safe = MagicMock(return_value=PipelineResult(
                    project_id="proj-1",
                    state=ProjectState.REQUIREMENTS_READY,
                    success=True,
                    message="ok",
                ))
                result = sup._run_discovery("proj-1", "build a todo app")

        return result, workspace

    def test_returns_requires_user_action(self):
        result, _ = self._run_discovery_to_sprint_planner()
        assert result.requires_user_action is True

    def test_returns_correct_action_needed(self):
        result, _ = self._run_discovery_to_sprint_planner()
        assert result.action_needed == "review_sprint_plan"

    def test_returns_sprint_plan_review_pending_state(self):
        result, _ = self._run_discovery_to_sprint_planner()
        assert result.state == ProjectState.SPRINT_PLAN_REVIEW_PENDING

    def test_returns_success_true(self):
        """Gate pause should be success=True — pipeline is working, not failed."""
        result, _ = self._run_discovery_to_sprint_planner()
        assert result.success is True

    def test_workspace_state_updated(self):
        """update_state must be called with SPRINT_PLAN_REVIEW_PENDING."""
        _, workspace = self._run_discovery_to_sprint_planner()
        workspace.update_state.assert_called_with("proj-1", ProjectState.SPRINT_PLAN_REVIEW_PENDING)


# ---------------------------------------------------------------------------
# 3: Quick mode auto-approves sprint_plan gate (no pause)
# ---------------------------------------------------------------------------

class TestSprintPlanGateQuickMode:

    def test_quick_mode_does_not_pause(self):
        """In quick mode, sprint_planner gate must not set SPRINT_PLAN_REVIEW_PENDING."""
        sup, workspace = _make_supervisor(quick_mode=True)

        with patch("app.workflow.pipeline_supervisor.get_discovery_stages",
                   return_value=["sprint_planner"]):
            with patch("app.workflow.stage_lookup.resolve_stage_name",
                       return_value="SprintPlanning"):
                sup._run_stage_safe = MagicMock(return_value=PipelineResult(
                    project_id="proj-q",
                    state=ProjectState.REQUIREMENTS_READY,
                    success=True,
                    message="ok",
                ))
                result = sup._run_discovery("proj-q", "request")

        # Quick mode: loop completes, state set to DESIGN_APPROVED, not SPRINT_PLAN_REVIEW_PENDING
        assert result.state == ProjectState.DESIGN_APPROVED
        assert result.requires_user_action is False
        # SPRINT_PLAN_REVIEW_PENDING must NOT have been set
        for c in workspace.update_state.call_args_list:
            assert c.args[1] != ProjectState.SPRINT_PLAN_REVIEW_PENDING


# ---------------------------------------------------------------------------
# 4-5: Architect and designer gates still work (non-regression)
# ---------------------------------------------------------------------------

class TestExistingGatesNonRegression:

    def _run_for_stage(self, stage_key: str, stage_value: str):
        sup, workspace = _make_supervisor(quick_mode=False)
        with patch("app.workflow.pipeline_supervisor.get_discovery_stages",
                   return_value=[stage_key]):
            with patch("app.workflow.stage_lookup.resolve_stage_name",
                       return_value=stage_value):
                sup._run_stage_safe = MagicMock(return_value=PipelineResult(
                    project_id="proj-reg",
                    state=ProjectState.REQUIREMENTS_READY,
                    success=True,
                    message="ok",
                ))
                return sup._run_discovery("proj-reg", "request"), workspace

    def test_architect_gate_still_sets_review_pending(self):
        result, workspace = self._run_for_stage("architect", "Architect")
        assert result.state == ProjectState.ARCHITECTURE_REVIEW_PENDING
        assert result.requires_user_action is True
        workspace.update_state.assert_called_with("proj-reg", ProjectState.ARCHITECTURE_REVIEW_PENDING)

    def test_designer_gate_still_sets_review_pending(self):
        result, workspace = self._run_for_stage("designer", "Designer")
        assert result.state == ProjectState.DESIGN_REVIEW_PENDING
        assert result.requires_user_action is True
        workspace.update_state.assert_called_with("proj-reg", ProjectState.DESIGN_REVIEW_PENDING)


# ---------------------------------------------------------------------------
# 6-7: WorkflowManager._await_gate and run() delegation
# ---------------------------------------------------------------------------

class TestWorkflowManagerGate:

    def _make_manager(self, state: ProjectState):
        from app.workflow.manager import WorkflowManager

        workspace = MagicMock()
        workspace.get_state.return_value = state
        workspace.load_project_json.return_value = {"stages_completed": []}

        with (
            patch("app.workflow.manager.PipelineSupervisor"),
            patch("app.workflow.sprint_executor.SprintExecutor"),
            patch("app.agents.factory.AgentFactory"),
            patch("app.config.manager.ConfigurationManager"),
            patch("app.workflow.change_manager.ChangeManager"),
            patch("app.workflow.impact_analyzer.ImpactAnalyzer"),
        ):
            engine = MagicMock()
            engine.workspace_manager = workspace
            engine.artifact_manager = MagicMock()
            engine.broadcaster = MagicMock()
            engine.memory_manager = None
            wm = WorkflowManager(engine=engine, workspace_manager=workspace)
        wm.workspace_manager = workspace
        return wm

    def test_await_gate_sprint_plan_returns_requires_user_action(self):
        wm = self._make_manager(ProjectState.SPRINT_PLAN_REVIEW_PENDING)
        result = wm._await_gate("proj-g", "sprint_plan")
        assert result.requires_user_action is True
        assert result.action_needed == "review_sprint_plan"

    def test_run_delegates_to_await_gate_when_sprint_plan_pending(self):
        wm = self._make_manager(ProjectState.SPRINT_PLAN_REVIEW_PENDING)
        wm._await_gate = MagicMock(return_value=PipelineResult(
            project_id="proj-g",
            state=ProjectState.SPRINT_PLAN_REVIEW_PENDING,
            success=False,
            requires_user_action=True,
        ))
        wm.run("proj-g", "build app")
        wm._await_gate.assert_called_once_with("proj-g", "sprint_plan")


# ---------------------------------------------------------------------------
# 8: _run_sprints SPRINT_PLAN_REVIEW_PENDING defence still works
# ---------------------------------------------------------------------------

class TestRunSprintsDefence:

    def test_run_sprints_returns_gate_when_pending(self):
        """_run_sprints must return requires_user_action=True when state is SPRINT_PLAN_REVIEW_PENDING."""
        sup, workspace = _make_supervisor()
        workspace.get_state.return_value = ProjectState.SPRINT_PLAN_REVIEW_PENDING
        workspace.load_project_json.return_value = {"completed_sprints": [], "stages_completed": []}

        result = sup._run_sprints("proj-s", "build app")

        assert result.requires_user_action is True
        assert result.action_needed == "review_sprint_plan"
        assert result.state == ProjectState.SPRINT_PLAN_REVIEW_PENDING


# ---------------------------------------------------------------------------
# 9: gates.py _assert_gate_state raises HTTP 409 for wrong state
# ---------------------------------------------------------------------------

class TestAssertGateState:

    def test_raises_409_for_wrong_state(self):
        from fastapi import HTTPException
        from app.api.gates import _assert_gate_state

        workspace = MagicMock()
        workspace.get_state.return_value = ProjectState.SPRINT_IN_PROGRESS  # wrong state
        with pytest.raises(HTTPException) as exc_info:
            _assert_gate_state("proj-409", "sprint_plan", workspace)
        assert exc_info.value.status_code == 409

    def test_passes_for_correct_state(self):
        from app.api.gates import _assert_gate_state

        workspace = MagicMock()
        workspace.get_state.return_value = ProjectState.SPRINT_PLAN_REVIEW_PENDING
        # Must not raise
        _assert_gate_state("proj-ok", "sprint_plan", workspace)


# ---------------------------------------------------------------------------
# 10: GateResult.to_dict() includes all required keys
# ---------------------------------------------------------------------------

class TestGateResult:

    def test_to_dict_includes_all_required_keys(self):
        from app.shared.dto.gate_result import GateResult

        gr = GateResult(
            status="resumed",
            project_id="proj-x",
            gate="sprint_plan",
            next_state="sprint_plan_ready",
            next_stage="Sprint Execution",
            message="Sprint plan approved.",
        )
        d = gr.to_dict()
        assert d["status"] == "resumed"
        assert d["project_id"] == "proj-x"
        assert d["gate"] == "sprint_plan"
        assert d["next_state"] == "sprint_plan_ready"
        assert d["next_stage"] == "Sprint Execution"
        assert d["message"] == "Sprint plan approved."
