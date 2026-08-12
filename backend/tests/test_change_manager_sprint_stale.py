"""test_change_manager_sprint_stale.py — Sprint plan staleness wiring in ChangeManager.

Verifies that apply() correctly sets stale=True and requirement_version_id on
the sprint_plan dict when code stages are affected by a confirmed change.

Running:
    cd backend
    python -m pytest tests/test_change_manager_sprint_stale.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.workflow.change_manager import ChangeManager


# ---------------------------------------------------------------------------
# Helpers — mirror the pattern in test_change_manager_req_version.py
# ---------------------------------------------------------------------------

_CHANGE_ID = "chg-sprint-stale-001"

_BASE_SPRINT_PLAN = {
    "project_id": "proj-1",
    "total_sprints": 2,
    "rationale": "Two sprints",
    "created_at": "2025-01-01T00:00:00+00:00",
    "stale": False,
    "requirement_version_id": None,
    "sprints": [
        {
            "sprint_id": "aaaa",
            "sprint_number": 1,
            "name": "Sprint 1",
            "goal": "Build auth",
            "status": "complete",
        },
        {
            "sprint_id": "bbbb",
            "sprint_number": 2,
            "name": "Sprint 2",
            "goal": "Build API",
            "status": "planned",
        },
    ],
}


def _make_impact_analyzer(affected_stages: list[str]) -> MagicMock:
    analysis = MagicMock()
    analysis.change_id = _CHANGE_ID
    analysis.affected_stages = affected_stages
    analysis.safe_stages = ["strategic_review"]
    import datetime
    analysis.analyzed_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    mock = MagicMock()
    mock.analyze.return_value = analysis
    return mock


def _make_manager(pj_state: dict, affected_stages: list[str]) -> tuple:
    workspace = MagicMock()
    state = dict(pj_state)

    def _load(pid):
        return dict(state)

    def _update(pid, updates):
        for k, v in updates.items():
            if v is None:
                state.pop(k, None)
            else:
                state[k] = v

    workspace.load_project_json.side_effect = _load
    workspace.update_project_json.side_effect = _update

    manager = ChangeManager(
        workspace_manager=workspace,
        impact_analyzer=_make_impact_analyzer(affected_stages),
        broadcaster=MagicMock(),
        transition_fn=MagicMock(),
    )
    return manager, state


def _pending(affected_stages: list[str]) -> dict:
    return {
        "change_id": _CHANGE_ID,
        "description": "Add OAuth login",
        "affected_stages": affected_stages,
        "safe_stages": ["strategic_review"],
        "analyzed_at": "2025-01-01T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Core staleness tests
# ---------------------------------------------------------------------------

class TestSprintPlanStaleness:

    def test_affected_code_stage_marks_plan_stale(self):
        """When backend is in affected_stages, sprint_plan.stale must become True."""
        affected = ["backend", "frontend", "qa"]
        manager, state = _make_manager(
            {
                "original_request": "Build an API",
                "stages_completed": ["strategic_review", "backend"],
                "sprint_plan": dict(_BASE_SPRINT_PLAN),
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert state["sprint_plan"]["stale"] is True

    def test_unaffected_non_code_stage_leaves_plan_fresh(self):
        """When only non-code stages are affected, sprint_plan.stale must stay False."""
        affected = ["strategic_review", "designer"]
        manager, state = _make_manager(
            {
                "original_request": "Build an API",
                "stages_completed": ["strategic_review"],
                "sprint_plan": dict(_BASE_SPRINT_PLAN),
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert state["sprint_plan"]["stale"] is False

    def test_requirement_version_id_set_on_stale_plan(self):
        """When plan is marked stale, requirement_version_id must be the new version ID."""
        affected = ["backend"]
        manager, state = _make_manager(
            {
                "original_request": "Build an API",
                "stages_completed": ["strategic_review", "backend"],
                "sprint_plan": dict(_BASE_SPRINT_PLAN),
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)

        new_version_id = state.get("current_requirement_version_id")
        assert new_version_id is not None, "RequirementVersion must have been created"
        assert state["sprint_plan"]["requirement_version_id"] == new_version_id

    def test_no_sprint_plan_does_not_raise(self):
        """When no sprint_plan exists in project.json, apply() must succeed silently."""
        affected = ["backend"]
        manager, state = _make_manager(
            {
                "original_request": "Build an API",
                "stages_completed": ["strategic_review"],
                # no sprint_plan key
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        result = manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert result["status"] == "applied"
        assert "sprint_plan" not in state  # not invented out of thin air

    def test_camelcase_backend_stage_also_marks_stale(self):
        """BackendDeveloper (CamelCase alias) must also trigger stale marking."""
        affected = ["BackendDeveloper"]
        manager, state = _make_manager(
            {
                "original_request": "Build an API",
                "stages_completed": ["strategic_review"],
                "sprint_plan": dict(_BASE_SPRINT_PLAN),
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert state["sprint_plan"]["stale"] is True

    def test_camelcase_frontend_stage_also_marks_stale(self):
        """FrontendDeveloper (CamelCase alias) must also trigger stale marking."""
        affected = ["FrontendDeveloper"]
        manager, state = _make_manager(
            {
                "original_request": "Build an API",
                "stages_completed": ["strategic_review"],
                "sprint_plan": dict(_BASE_SPRINT_PLAN),
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert state["sprint_plan"]["stale"] is True

    def test_requirement_version_id_unchanged_for_non_code_change(self):
        """sprint_plan.requirement_version_id must not change for non-code changes."""
        affected = ["strategic_review"]
        original_vid = "original-version-uuid"
        plan = {**_BASE_SPRINT_PLAN, "requirement_version_id": original_vid}
        manager, state = _make_manager(
            {
                "original_request": "Build an API",
                "stages_completed": ["strategic_review"],
                "sprint_plan": plan,
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert state["sprint_plan"]["requirement_version_id"] == original_vid


# ---------------------------------------------------------------------------
# Existing ChangeManager behavior preserved
# ---------------------------------------------------------------------------

class TestExistingBehaviorPreserved:

    def test_stages_completed_still_trimmed(self):
        """apply() must still remove affected stages from stages_completed."""
        affected = ["backend"]
        manager, state = _make_manager(
            {
                "original_request": "x",
                "stages_completed": ["strategic_review", "backend"],
                "sprint_plan": dict(_BASE_SPRINT_PLAN),
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert "backend" not in state["stages_completed"]
        assert "strategic_review" in state["stages_completed"]

    def test_pending_change_cleared(self):
        """apply() must clear pending_change regardless of sprint staleness."""
        affected = ["backend"]
        manager, state = _make_manager(
            {
                "original_request": "x",
                "stages_completed": [],
                "sprint_plan": dict(_BASE_SPRINT_PLAN),
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert state.get("pending_change") is None

    def test_cancelled_change_does_not_touch_sprint_plan(self):
        """Cancelled (confirmed=False) apply must not modify sprint_plan."""
        plan = {**_BASE_SPRINT_PLAN}
        manager, state = _make_manager(
            {
                "stages_completed": ["strategic_review"],
                "sprint_plan": plan,
                "pending_change": {"change_id": _CHANGE_ID},
            },
            affected_stages=["backend"],
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=False)
        assert state["sprint_plan"]["stale"] is False
        assert state["sprint_plan"]["requirement_version_id"] is None

    def test_requirement_version_still_created(self):
        """RequirementVersion must still be created alongside sprint staleness."""
        affected = ["backend"]
        manager, state = _make_manager(
            {
                "original_request": "Build something",
                "stages_completed": ["strategic_review"],
                "sprint_plan": dict(_BASE_SPRINT_PLAN),
                "pending_change": _pending(affected),
            },
            affected_stages=affected,
        )
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert len(state.get("requirement_versions", [])) == 1
        assert state.get("current_requirement_version_id") is not None
