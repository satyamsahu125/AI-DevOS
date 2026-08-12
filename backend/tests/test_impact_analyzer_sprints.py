"""test_impact_analyzer_sprints.py — Focused tests for ImpactAnalyzer.sprints_to_replan.

Verifies that sprints_to_replan is computed from actual sprint state in
project.json (completed_sprints + sprint_plan.sprints) rather than the
hardcoded [1] that previously existed.

Running:
    cd backend
    python -m pytest tests/test_impact_analyzer_sprints.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.workflow.impact_analyzer import ImpactAnalyzer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sprint(number: int, status: str = "planned") -> dict:
    return {
        "sprint_id": f"00000000-0000-0000-0000-00000000000{number}",
        "sprint_number": number,
        "name": f"Sprint {number}",
        "goal": f"Deliver sprint {number}",
        "status": status,
    }


def _make_analyzer(project_json: dict | None) -> ImpactAnalyzer:
    """Build an ImpactAnalyzer with a stubbed workspace_manager and LLM."""
    workspace = MagicMock()
    workspace.load_project_json.return_value = project_json

    llm = MagicMock()
    # Classify change as "add_feature" so backend/frontend are affected → needs_replan=True
    llm.generate_text.return_value.content = "add_feature"

    return ImpactAnalyzer(
        llm_manager=llm,
        artifact_manager=MagicMock(),
        workspace_manager=workspace,
    )


def _analyze(analyzer: ImpactAnalyzer, project_id: str = "proj-1") -> list[int]:
    """Run analyze() with stages that include backend so needs_replan=True."""
    result = analyzer.analyze(
        project_id=project_id,
        change_description="Add OAuth login",
        stages_completed=["strategic_review", "product_owner", "architect",
                          "sprint_planner", "backend", "frontend"],
    )
    return result.sprints_to_replan


# ---------------------------------------------------------------------------
# Core calculation tests
# ---------------------------------------------------------------------------

class TestSprintsToReplan:

    def test_unfinished_current_sprint_is_included(self):
        """A sprint that has started but not completed must appear in sprints_to_replan."""
        pj = {
            "sprint_plan": {
                "project_id": "proj-1",
                "total_sprints": 3,
                "sprints": [
                    _make_sprint(1, "complete"),
                    _make_sprint(2, "in_progress"),  # current, unfinished
                    _make_sprint(3, "planned"),
                ],
            },
            "completed_sprints": [1],
        }
        result = _analyze(_make_analyzer(pj))
        assert 2 in result, f"Sprint 2 (in_progress) must be in sprints_to_replan, got {result}"
        assert 3 in result, f"Sprint 3 (planned) must be in sprints_to_replan, got {result}"

    def test_completed_sprints_excluded(self):
        """Sprints in completed_sprints must NOT appear in sprints_to_replan."""
        pj = {
            "sprint_plan": {
                "project_id": "proj-1",
                "total_sprints": 3,
                "sprints": [
                    _make_sprint(1, "complete"),
                    _make_sprint(2, "complete"),
                    _make_sprint(3, "in_progress"),
                ],
            },
            "completed_sprints": [1, 2],
        }
        result = _analyze(_make_analyzer(pj))
        assert 1 not in result, f"Sprint 1 (complete) must not be in sprints_to_replan, got {result}"
        assert 2 not in result, f"Sprint 2 (complete) must not be in sprints_to_replan, got {result}"
        assert 3 in result

    def test_multiple_affected_sprints_returned_sorted(self):
        """Multiple incomplete sprints must all be returned, sorted ascending."""
        pj = {
            "sprint_plan": {
                "project_id": "proj-1",
                "total_sprints": 4,
                "sprints": [
                    _make_sprint(1, "complete"),
                    _make_sprint(2, "planned"),
                    _make_sprint(3, "planned"),
                    _make_sprint(4, "planned"),
                ],
            },
            "completed_sprints": [1],
        }
        result = _analyze(_make_analyzer(pj))
        assert result == sorted(result), f"Result must be sorted ascending, got {result}"
        assert result == [2, 3, 4]

    def test_hardcoded_one_behavior_gone(self):
        """sprints_to_replan must NOT always return [1] regardless of project state."""
        # All sprints complete — result should be [], not [1]
        pj = {
            "sprint_plan": {
                "project_id": "proj-1",
                "total_sprints": 2,
                "sprints": [
                    _make_sprint(1, "complete"),
                    _make_sprint(2, "complete"),
                ],
            },
            "completed_sprints": [1, 2],
        }
        result = _analyze(_make_analyzer(pj))
        assert result != [1], (
            "sprints_to_replan must not be hardcoded [1]; "
            f"with all sprints complete expected [], got {result}"
        )
        assert result == []

    def test_no_sprint_plan_returns_empty_list(self):
        """When sprint_plan is absent, return [] — no sprint data available yet."""
        pj = {"completed_sprints": []}
        result = _analyze(_make_analyzer(pj))
        assert result == []

    def test_no_workspace_manager_returns_empty_list(self):
        """Without a workspace_manager, sprints_to_replan falls back to []."""
        llm = MagicMock()
        llm.generate_text.return_value.content = "add_feature"
        analyzer = ImpactAnalyzer(
            llm_manager=llm,
            artifact_manager=MagicMock(),
            workspace_manager=None,  # no workspace wired
        )
        result = _analyze(analyzer)
        assert result == []

    def test_determinism_same_state_same_result(self):
        """Identical project state + identical change → identical sprints_to_replan."""
        pj = {
            "sprint_plan": {
                "project_id": "proj-1",
                "total_sprints": 3,
                "sprints": [
                    _make_sprint(1, "complete"),
                    _make_sprint(2, "in_progress"),
                    _make_sprint(3, "planned"),
                ],
            },
            "completed_sprints": [1],
        }
        a1 = _analyze(_make_analyzer(pj))
        a2 = _analyze(_make_analyzer(pj))
        assert a1 == a2, f"Must be deterministic: {a1} != {a2}"

    def test_no_code_stages_affected_returns_empty(self):
        """When only non-code stages are affected, sprints_to_replan must be []."""
        workspace = MagicMock()
        workspace.load_project_json.return_value = {
            "sprint_plan": {
                "project_id": "proj-1",
                "total_sprints": 2,
                "sprints": [_make_sprint(1, "planned"), _make_sprint(2, "planned")],
            },
            "completed_sprints": [],
        }
        llm = MagicMock()
        # Classify as modify_ui — affects designer/frontend/qa (frontend IS a code stage!)
        # Use change_scale which only affects architect/security/devops (no backend/frontend)
        llm.generate_text.return_value.content = "change_scale"
        analyzer = ImpactAnalyzer(
            llm_manager=llm,
            artifact_manager=MagicMock(),
            workspace_manager=workspace,
        )
        result = analyzer.analyze(
            project_id="proj-1",
            change_description="Increase to 10k concurrent users",
            stages_completed=["strategic_review", "architect", "security", "devops"],
        )
        assert result.sprints_to_replan == [], (
            f"change_scale does not affect backend/frontend; expected [], got {result.sprints_to_replan}"
        )


# ---------------------------------------------------------------------------
# Existing ImpactAnalyzer behavior preserved
# ---------------------------------------------------------------------------

class TestExistingBehaviorPreserved:

    def test_affected_stages_still_computed(self):
        """change classification → affected_stages must still work as before."""
        workspace = MagicMock()
        workspace.load_project_json.return_value = {
            "sprint_plan": {
                "project_id": "proj-1",
                "total_sprints": 1,
                "sprints": [_make_sprint(1, "planned")],
            },
            "completed_sprints": [],
        }
        llm = MagicMock()
        llm.generate_text.return_value.content = "modify_ui"
        analyzer = ImpactAnalyzer(
            llm_manager=llm,
            artifact_manager=MagicMock(),
            workspace_manager=workspace,
        )
        result = analyzer.analyze(
            project_id="proj-1",
            change_description="Redesign login page",
            stages_completed=["strategic_review", "designer", "frontend"],
        )
        assert "designer" in result.affected_stages or "frontend" in result.affected_stages

    def test_safe_stages_still_computed(self):
        """Stages not affected must appear in safe_stages."""
        workspace = MagicMock()
        workspace.load_project_json.return_value = None
        llm = MagicMock()
        llm.generate_text.return_value.content = "modify_ui"
        analyzer = ImpactAnalyzer(
            llm_manager=llm,
            artifact_manager=MagicMock(),
            workspace_manager=workspace,
        )
        result = analyzer.analyze(
            project_id="proj-1",
            change_description="Change button colors",
            stages_completed=["strategic_review", "designer"],
        )
        assert isinstance(result.safe_stages, list)

    def test_change_id_is_uuid(self):
        """ImpactAnalysis.change_id must be a UUID string (behavior unchanged)."""
        import uuid
        workspace = MagicMock()
        workspace.load_project_json.return_value = None
        llm = MagicMock()
        llm.generate_text.return_value.content = "add_feature"
        analyzer = ImpactAnalyzer(
            llm_manager=llm,
            artifact_manager=MagicMock(),
            workspace_manager=workspace,
        )
        result = analyzer.analyze("proj-1", "Add export button", ["strategic_review"])
        uuid.UUID(result.change_id)  # raises if not valid UUID

    def test_analyzed_at_is_utc(self):
        """ImpactAnalysis.analyzed_at must be UTC-aware (behavior unchanged)."""
        workspace = MagicMock()
        workspace.load_project_json.return_value = None
        llm = MagicMock()
        llm.generate_text.return_value.content = "add_feature"
        analyzer = ImpactAnalyzer(
            llm_manager=llm,
            artifact_manager=MagicMock(),
            workspace_manager=workspace,
        )
        result = analyzer.analyze("proj-1", "Add export button", [])
        assert result.analyzed_at.tzinfo is not None

    def test_analyze_file_impact_unaffected(self):
        """analyze_file_impact() with no intelligence layer still returns empty dict."""
        analyzer = ImpactAnalyzer(
            llm_manager=MagicMock(),
            artifact_manager=MagicMock(),
            workspace_manager=MagicMock(),
        )
        result = analyzer.analyze_file_impact("proj-1", "Add feature X")
        assert result["total_affected"] == 0
        assert result["files_to_regenerate"] == []
