"""test_requirement_version.py — Unit tests for RequirementVersion model.

Covers:
  - Valid construction with all required fields.
  - Auto-generated version_id (UUID4).
  - Default field values.
  - supersedes=None for the first version.
  - Superseding another version via .supersede().
  - All four RequirementVersionStatus values.
  - to_dict() / from_dict() round-trip.
  - UTC enforcement on created_at.
  - Validation errors for empty content and empty project_id.

Running:
    cd backend
    python -m pytest tests/test_requirement_version.py -v
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from pydantic import ValidationError

from app.shared.enums.requirement_version_status import RequirementVersionStatus
from app.shared.models.requirement_version import RequirementVersion


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestRequirementVersionConstruction:

    def test_minimal_construction(self):
        """Only project_id and content are required; all other fields default."""
        rv = RequirementVersion(project_id="proj-1", content="Build a todo app")
        assert rv.project_id == "proj-1"
        assert rv.content == "Build a todo app"

    def test_version_id_auto_generated(self):
        """version_id is a valid UUID4 string when not supplied."""
        rv = RequirementVersion(project_id="proj-1", content="Build a todo app")
        parsed = uuid.UUID(rv.version_id)   # raises ValueError if not a valid UUID
        assert parsed.version == 4

    def test_version_id_is_unique_per_instance(self):
        """Each RequirementVersion gets a distinct version_id."""
        rv1 = RequirementVersion(project_id="p", content="v1")
        rv2 = RequirementVersion(project_id="p", content="v2")
        assert rv1.version_id != rv2.version_id

    def test_explicit_version_id_accepted(self):
        """Caller may supply a specific version_id."""
        fixed = str(uuid.uuid4())
        rv = RequirementVersion(project_id="p", content="c", version_id=fixed)
        assert rv.version_id == fixed

    def test_default_status_is_current(self):
        """New versions default to CURRENT status."""
        rv = RequirementVersion(project_id="p", content="c")
        assert rv.status == RequirementVersionStatus.CURRENT

    def test_default_supersedes_is_none(self):
        """First version has no predecessor."""
        rv = RequirementVersion(project_id="p", content="c")
        assert rv.supersedes is None

    def test_default_created_by_is_system(self):
        rv = RequirementVersion(project_id="p", content="c")
        assert rv.created_by == "system"

    def test_default_change_description_is_empty(self):
        rv = RequirementVersion(project_id="p", content="c")
        assert rv.change_description == ""

    def test_created_at_is_utc_aware(self):
        """Auto-generated created_at must be timezone-aware (UTC)."""
        rv = RequirementVersion(project_id="p", content="c")
        assert rv.created_at.tzinfo is not None


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------

class TestRequirementVersionStatus:

    def test_all_four_status_values_accepted(self):
        for status in RequirementVersionStatus:
            rv = RequirementVersion(project_id="p", content="c", status=status)
            assert rv.status == status

    def test_current_value(self):
        assert RequirementVersionStatus.CURRENT.value == "current"

    def test_superseded_value(self):
        assert RequirementVersionStatus.SUPERSEDED.value == "superseded"

    def test_proposed_value(self):
        assert RequirementVersionStatus.PROPOSED.value == "proposed"

    def test_rejected_value(self):
        assert RequirementVersionStatus.REJECTED.value == "rejected"

    def test_status_from_string(self):
        """String values are accepted (Pydantic coercion via str, Enum)."""
        rv = RequirementVersion(project_id="p", content="c", status="superseded")
        assert rv.status == RequirementVersionStatus.SUPERSEDED


# ---------------------------------------------------------------------------
# supersedes / version chain
# ---------------------------------------------------------------------------

class TestSupersedes:

    def test_first_version_has_no_predecessor(self):
        rv = RequirementVersion(project_id="p", content="Initial requirements")
        assert rv.supersedes is None

    def test_explicit_supersedes_stored(self):
        prior_id = str(uuid.uuid4())
        rv = RequirementVersion(
            project_id="p",
            content="v2",
            supersedes=prior_id,
            status=RequirementVersionStatus.CURRENT,
        )
        assert rv.supersedes == prior_id

    def test_supersede_method_links_to_current_version(self):
        """RequirementVersion.supersede() returns a new version pointing back to self."""
        v1 = RequirementVersion(project_id="p", content="Initial requirements")
        v2 = v1.supersede("Added authentication", created_by="user")

        assert v2.supersedes == v1.version_id
        assert v2.status == RequirementVersionStatus.CURRENT
        assert v2.project_id == v1.project_id
        assert v2.change_description == "Added authentication"
        assert v2.created_by == "user"

    def test_supersede_method_generates_new_version_id(self):
        v1 = RequirementVersion(project_id="p", content="v1")
        v2 = v1.supersede("changed")
        assert v2.version_id != v1.version_id

    def test_supersede_does_not_mutate_original(self):
        """The original version is not modified by .supersede()."""
        v1 = RequirementVersion(project_id="p", content="v1")
        original_id = v1.version_id
        original_status = v1.status
        _ = v1.supersede("changed")
        assert v1.version_id == original_id
        assert v1.status == original_status


# ---------------------------------------------------------------------------
# Datetime / UTC enforcement
# ---------------------------------------------------------------------------

class TestDatetimeHandling:

    def test_naive_datetime_coerced_to_utc(self):
        naive = datetime(2025, 1, 1, 12, 0, 0)  # no tzinfo
        rv = RequirementVersion(project_id="p", content="c", created_at=naive)
        assert rv.created_at.tzinfo is not None

    def test_iso_string_parsed_to_utc_datetime(self):
        rv = RequirementVersion(
            project_id="p", content="c", created_at="2025-06-15T10:30:00+00:00"
        )
        assert isinstance(rv.created_at, datetime)
        assert rv.created_at.tzinfo is not None

    def test_aware_datetime_preserved(self):
        aware = datetime(2025, 3, 20, 8, 0, 0, tzinfo=timezone.utc)
        rv = RequirementVersion(project_id="p", content="c", created_at=aware)
        assert rv.created_at == aware


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

class TestValidation:

    def test_empty_content_raises(self):
        with pytest.raises(ValidationError):
            RequirementVersion(project_id="p", content="")

    def test_whitespace_content_raises(self):
        with pytest.raises(ValidationError):
            RequirementVersion(project_id="p", content="   ")

    def test_empty_project_id_raises(self):
        with pytest.raises(ValidationError):
            RequirementVersion(project_id="", content="some requirement")

    def test_whitespace_project_id_raises(self):
        with pytest.raises(ValidationError):
            RequirementVersion(project_id="  ", content="some requirement")


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:

    def test_to_dict_contains_all_fields(self):
        rv = RequirementVersion(
            project_id="proj-x",
            content="Build a calendar app",
            change_description="Initial version",
            created_by="user",
        )
        d = rv.to_dict()
        assert d["version_id"] == rv.version_id
        assert d["project_id"] == "proj-x"
        assert d["content"] == "Build a calendar app"
        assert d["change_description"] == "Initial version"
        assert d["supersedes"] is None
        assert d["status"] == "current"
        assert isinstance(d["created_at"], str)   # ISO string
        assert d["created_by"] == "user"

    def test_from_dict_round_trip(self):
        rv = RequirementVersion(
            project_id="proj-y",
            content="Add payments",
            supersedes=str(uuid.uuid4()),
            status=RequirementVersionStatus.SUPERSEDED,
            created_by="user",
        )
        restored = RequirementVersion.from_dict(rv.to_dict())
        assert restored.version_id == rv.version_id
        assert restored.project_id == rv.project_id
        assert restored.content == rv.content
        assert restored.supersedes == rv.supersedes
        assert restored.status == rv.status
        assert restored.created_by == rv.created_by
        assert restored.created_at == rv.created_at

    def test_from_dict_tolerates_missing_optional_fields(self):
        """Minimal dict (no supersedes, no change_description) loads without error."""
        data = {
            "project_id": "p",
            "content": "some requirement",
        }
        rv = RequirementVersion.from_dict(data)
        assert rv.project_id == "p"
        assert rv.supersedes is None
        assert rv.change_description == ""

    def test_status_serialized_as_string(self):
        rv = RequirementVersion(
            project_id="p", content="c", status=RequirementVersionStatus.PROPOSED
        )
        d = rv.to_dict()
        assert d["status"] == "proposed"
        assert isinstance(d["status"], str)
