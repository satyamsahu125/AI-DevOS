"""test_change_manager_req_version.py — AC-P2-01 integration tests.

Verifies that ChangeManager.apply() correctly creates and persists
RequirementVersion records and keeps current_requirement_version_id current.

Running:
    cd backend
    python -m pytest tests/test_change_manager_req_version.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from app.shared.enums.requirement_version_status import RequirementVersionStatus
from app.shared.models.requirement_version import RequirementVersion
from app.workflow.change_manager import ChangeManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CHANGE_ID = "change-001"


def _make_impact_analyzer(change_id: str = _CHANGE_ID) -> MagicMock:
    analysis = MagicMock()
    analysis.change_id = change_id
    analysis.affected_stages = ["BackendDeveloper"]
    analysis.safe_stages = ["StrategicReview"]
    analysis.analyzed_at = __import__("datetime").datetime(
        2025, 1, 1, tzinfo=__import__("datetime").timezone.utc
    )
    mock = MagicMock()
    mock.analyze.return_value = analysis
    return mock


def _make_manager(pj_state: dict) -> tuple[ChangeManager, MagicMock]:
    """Return (ChangeManager, workspace_mock) with pj_state pre-loaded."""
    workspace = MagicMock()

    # Simulate atomic update: merge each update call into a local dict so that
    # subsequent load_project_json calls reflect earlier writes.
    state = dict(pj_state)

    def _load(pid):
        return dict(state)

    def _update(pid, updates):
        # Remove None-valued keys (matches project.json semantics for "clear field")
        for k, v in updates.items():
            if v is None:
                state.pop(k, None)
            else:
                state[k] = v

    workspace.load_project_json.side_effect = _load
    workspace.update_project_json.side_effect = _update

    manager = ChangeManager(
        workspace_manager=workspace,
        impact_analyzer=_make_impact_analyzer(),
        broadcaster=MagicMock(),
        transition_fn=MagicMock(),
    )
    return manager, workspace, state


# ---------------------------------------------------------------------------
# AC-P2-01: First change creates a CURRENT RequirementVersion
# ---------------------------------------------------------------------------

class TestFirstRequirementChange:

    def _apply_first_change(self, original_request: str = "Build a todo app") -> tuple:
        manager, workspace, state = _make_manager({
            "original_request": original_request,
            "stages_completed": ["StrategicReview"],
            "pending_change": {
                "change_id": _CHANGE_ID,
                "description": "Add user authentication",
                "affected_stages": ["BackendDeveloper"],
                "safe_stages": ["StrategicReview"],
                "analyzed_at": "2025-01-01T00:00:00+00:00",
            },
        })
        result = manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        return result, state

    def test_apply_returns_applied_status(self):
        result, _ = self._apply_first_change()
        assert result["status"] == "applied"

    def test_first_change_creates_requirement_version(self):
        _, state = self._apply_first_change()
        versions = state.get("requirement_versions", [])
        assert len(versions) == 1, f"Expected 1 version, got {len(versions)}"

    def test_first_version_is_current(self):
        _, state = self._apply_first_change()
        v = state["requirement_versions"][0]
        assert v["status"] == RequirementVersionStatus.CURRENT.value

    def test_current_version_id_is_set(self):
        _, state = self._apply_first_change()
        assert "current_requirement_version_id" in state
        assert state["current_requirement_version_id"] == state["requirement_versions"][0]["version_id"]

    def test_first_version_has_no_supersedes(self):
        _, state = self._apply_first_change()
        v = state["requirement_versions"][0]
        assert v["supersedes"] is None

    def test_first_version_content_uses_original_request(self):
        _, state = self._apply_first_change("Build a todo app")
        v = state["requirement_versions"][0]
        assert "Build a todo app" in v["content"]

    def test_first_version_stores_change_description(self):
        _, state = self._apply_first_change()
        v = state["requirement_versions"][0]
        assert v["change_description"] == "Add user authentication"

    def test_first_version_created_by_user(self):
        _, state = self._apply_first_change()
        v = state["requirement_versions"][0]
        assert v["created_by"] == "user"

    def test_first_version_project_id_correct(self):
        _, state = self._apply_first_change()
        v = state["requirement_versions"][0]
        assert v["project_id"] == "proj-1"

    def test_first_version_has_valid_version_id(self):
        import uuid
        _, state = self._apply_first_change()
        v = state["requirement_versions"][0]
        uuid.UUID(v["version_id"])  # raises if invalid

    def test_first_version_has_utc_created_at(self):
        _, state = self._apply_first_change()
        v = state["requirement_versions"][0]
        assert "T" in v["created_at"]  # ISO format with time component


# ---------------------------------------------------------------------------
# AC-P2-01: Second change supersedes the first
# ---------------------------------------------------------------------------

class TestSecondRequirementChange:

    def _apply_two_changes(self) -> dict:
        # Simulate state after first change was applied
        first_version = RequirementVersion(
            project_id="proj-1",
            content="Build a todo app",
            change_description="Initial version",
            supersedes=None,
            status=RequirementVersionStatus.CURRENT,
            created_by="user",
        )
        initial_state = {
            "original_request": "Build a todo app",
            "stages_completed": ["StrategicReview"],
            "requirement_versions": [first_version.to_dict()],
            "current_requirement_version_id": first_version.version_id,
            "pending_change": {
                "change_id": "change-002",
                "description": "Add dark mode",
                "affected_stages": ["FrontendDeveloper"],
                "safe_stages": ["StrategicReview"],
                "analyzed_at": "2025-01-02T00:00:00+00:00",
            },
        }
        manager, workspace, state = _make_manager(initial_state)
        manager.apply("proj-1", "change-002", confirmed=True)
        return state, first_version.version_id

    def test_exactly_two_versions_after_two_changes(self):
        state, _ = self._apply_two_changes()
        assert len(state["requirement_versions"]) == 2

    def test_second_version_is_current(self):
        state, _ = self._apply_two_changes()
        current_id = state["current_requirement_version_id"]
        current = next(v for v in state["requirement_versions"] if v["version_id"] == current_id)
        assert current["status"] == RequirementVersionStatus.CURRENT.value

    def test_first_version_becomes_superseded(self):
        state, first_id = self._apply_two_changes()
        first = next(v for v in state["requirement_versions"] if v["version_id"] == first_id)
        assert first["status"] == RequirementVersionStatus.SUPERSEDED.value

    def test_only_one_current_version(self):
        state, _ = self._apply_two_changes()
        current_versions = [
            v for v in state["requirement_versions"]
            if v["status"] == RequirementVersionStatus.CURRENT.value
        ]
        assert len(current_versions) == 1

    def test_second_version_supersedes_first(self):
        state, first_id = self._apply_two_changes()
        current_id = state["current_requirement_version_id"]
        second = next(v for v in state["requirement_versions"] if v["version_id"] == current_id)
        assert second["supersedes"] == first_id

    def test_second_version_change_description_correct(self):
        state, _ = self._apply_two_changes()
        current_id = state["current_requirement_version_id"]
        second = next(v for v in state["requirement_versions"] if v["version_id"] == current_id)
        assert second["change_description"] == "Add dark mode"

    def test_second_version_content_includes_previous(self):
        state, _ = self._apply_two_changes()
        current_id = state["current_requirement_version_id"]
        second = next(v for v in state["requirement_versions"] if v["version_id"] == current_id)
        # Content must include the base + the change description
        assert "Build a todo app" in second["content"]
        assert "Add dark mode" in second["content"]

    def test_current_version_id_points_to_second(self):
        state, first_id = self._apply_two_changes()
        current_id = state["current_requirement_version_id"]
        assert current_id != first_id  # must have advanced to new version


# ---------------------------------------------------------------------------
# Persistence / round-trip
# ---------------------------------------------------------------------------

class TestPersistence:

    def test_versions_survive_reload_via_from_dict(self):
        """to_dict() / from_dict() round-trip for a version stored in project.json."""
        manager, workspace, state = _make_manager({
            "original_request": "Build an API",
            "stages_completed": [],
            "pending_change": {
                "change_id": _CHANGE_ID,
                "description": "Add rate limiting",
                "affected_stages": ["BackendDeveloper"],
                "safe_stages": [],
                "analyzed_at": "2025-01-01T00:00:00+00:00",
            },
        })
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)

        # Simulate process restart: reload raw dict from project.json and reconstruct
        raw_version = state["requirement_versions"][0]
        restored = RequirementVersion.from_dict(raw_version)

        assert restored.version_id == raw_version["version_id"]
        assert restored.project_id == "proj-1"
        assert restored.content == raw_version["content"]
        assert restored.status == RequirementVersionStatus.CURRENT
        assert restored.supersedes is None


# ---------------------------------------------------------------------------
# Existing ChangeManager behavior preserved
# ---------------------------------------------------------------------------

class TestExistingBehaviorPreserved:

    def test_cancelled_change_returns_cancelled(self):
        manager, workspace, state = _make_manager({
            "pending_change": {"change_id": _CHANGE_ID},
        })
        result = manager.apply("proj-1", _CHANGE_ID, confirmed=False)
        assert result["status"] == "cancelled"

    def test_cancelled_change_creates_no_version(self):
        manager, workspace, state = _make_manager({
            "pending_change": {"change_id": _CHANGE_ID},
        })
        manager.apply("proj-1", _CHANGE_ID, confirmed=False)
        assert state.get("requirement_versions") is None
        assert state.get("current_requirement_version_id") is None

    def test_confirmed_change_still_updates_stages_completed(self):
        manager, workspace, state = _make_manager({
            "original_request": "Build something",
            "stages_completed": ["StrategicReview", "BackendDeveloper"],
            "pending_change": {
                "change_id": _CHANGE_ID,
                "description": "change something",
                "affected_stages": ["BackendDeveloper"],
                "safe_stages": ["StrategicReview"],
                "analyzed_at": "2025-01-01T00:00:00+00:00",
            },
        })
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        assert state["stages_completed"] == ["StrategicReview"]

    def test_confirmed_change_appends_to_requirement_changes(self):
        manager, workspace, state = _make_manager({
            "original_request": "Build something",
            "stages_completed": [],
            "requirement_changes": [],
            "pending_change": {
                "change_id": _CHANGE_ID,
                "description": "Add feature X",
                "affected_stages": [],
                "safe_stages": [],
                "analyzed_at": "2025-01-01T00:00:00+00:00",
            },
        })
        manager.apply("proj-1", _CHANGE_ID, confirmed=True)
        changes = state["requirement_changes"]
        assert len(changes) == 1
        assert changes[0]["change_id"] == _CHANGE_ID
        assert changes[0]["description"] == "Add feature X"

    def test_wrong_change_id_raises(self):
        manager, workspace, state = _make_manager({
            "original_request": "x",
            "pending_change": {
                "change_id": "correct-id",
                "description": "d",
                "affected_stages": [],
                "safe_stages": [],
                "analyzed_at": "2025-01-01T00:00:00+00:00",
            },
        })
        with pytest.raises(ValueError, match="Change ID mismatch"):
            manager.apply("proj-1", "wrong-id", confirmed=True)
