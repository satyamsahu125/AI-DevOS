"""test_sprint_plan_model.py — Focused tests for SprintPlan model extensions.

Covers:
  - stale defaults to False
  - requirement_version_id defaults to None
  - Both fields can be explicitly set
  - Existing data without the fields deserializes successfully
  - Serialization includes both fields

Running:
    cd backend
    python -m pytest tests/test_sprint_plan_model.py -v
"""
from __future__ import annotations

from app.shared.models.sprint import SprintPlan


_MINIMAL = {"project_id": "proj-1", "total_sprints": 2}


class TestSprintPlanExtensions:

    def test_stale_defaults_to_false(self):
        plan = SprintPlan(**_MINIMAL)
        assert plan.stale is False

    def test_requirement_version_id_defaults_to_none(self):
        plan = SprintPlan(**_MINIMAL)
        assert plan.requirement_version_id is None

    def test_stale_can_be_set_true(self):
        plan = SprintPlan(**_MINIMAL, stale=True)
        assert plan.stale is True

    def test_requirement_version_id_can_be_set(self):
        vid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        plan = SprintPlan(**_MINIMAL, requirement_version_id=vid)
        assert plan.requirement_version_id == vid

    def test_existing_data_without_fields_loads(self):
        """project.json records without stale/requirement_version_id must still parse."""
        data = {
            "project_id": "proj-2",
            "total_sprints": 3,
            "sprints": [],
            "rationale": "Three sprints",
            # stale and requirement_version_id deliberately absent
        }
        plan = SprintPlan.model_validate(data)
        assert plan.stale is False
        assert plan.requirement_version_id is None

    def test_serialization_includes_stale(self):
        plan = SprintPlan(**_MINIMAL, stale=True)
        d = plan.model_dump(mode="json")
        assert "stale" in d
        assert d["stale"] is True

    def test_serialization_includes_requirement_version_id(self):
        vid = "11111111-2222-3333-4444-555555555555"
        plan = SprintPlan(**_MINIMAL, requirement_version_id=vid)
        d = plan.model_dump(mode="json")
        assert "requirement_version_id" in d
        assert d["requirement_version_id"] == vid

    def test_serialization_requirement_version_id_none_when_unset(self):
        plan = SprintPlan(**_MINIMAL)
        d = plan.model_dump(mode="json")
        assert d["requirement_version_id"] is None
