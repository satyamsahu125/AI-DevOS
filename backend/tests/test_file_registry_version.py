"""test_file_registry_version.py — FileRegistry requirement_version_id tracking.

Verifies:
  1. A newly registered file receives the current requirement_version_id.
  2. A file registered when no requirement version exists has None.
  3. Existing entries without the field load without error (backward compat).
  4. Serialization/deserialization preserves the field through the JSON layer.
  5. Updating/re-registering a file updates requirement_version_id without
     corrupting unrelated fields (path, created_sprint).
  6. record_many() stamps all entries with the same version ID.
  7. workspace_manager failure during version read is non-fatal.

Running:
    cd backend
    python -m pytest tests/test_file_registry_version.py -v
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.workspace.file_registry import FileRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VID = "req-v-abc-001"
_VID2 = "req-v-abc-002"


def _make_workspace(
    root: Path,
    version_id: str | None = _VID,
    raises: bool = False,
) -> MagicMock:
    ws = MagicMock()
    ws.get_workspace_path.return_value = root
    if raises:
        ws.load_project_json.side_effect = RuntimeError("disk failure")
    else:
        pj: dict = {}
        if version_id is not None:
            pj["current_requirement_version_id"] = version_id
        ws.load_project_json.return_value = pj
    return ws


def _make_registry(root: Path, version_id: str | None = _VID, raises: bool = False) -> FileRegistry:
    ws = _make_workspace(root, version_id, raises)
    return FileRegistry(workspace_manager=ws)


def _registry_path(root: Path) -> Path:
    return root / "artifacts" / "file_registry.json"


def _read_registry(root: Path) -> dict:
    p = _registry_path(root)
    return json.loads(p.read_text()) if p.exists() else {}


# ---------------------------------------------------------------------------
# record() — new file
# ---------------------------------------------------------------------------

class TestRecordNewFile:

    def test_new_file_gets_version_id(self):
        """A newly registered file must have requirement_version_id set."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.record("proj-1", "backend/models/user.py", sprint_number=1)

            entry = reg.get("proj-1", "backend/models/user.py")
            assert entry is not None
            assert entry["requirement_version_id"] == _VID

    def test_new_file_no_version_gets_none(self):
        """When no requirement version exists, requirement_version_id must be None."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td), version_id=None)
            reg.record("proj-1", "backend/api/routes.py", sprint_number=1)

            entry = reg.get("proj-1", "backend/api/routes.py")
            assert entry is not None
            assert entry["requirement_version_id"] is None

    def test_new_file_preserves_sprint_fields(self):
        """requirement_version_id must not displace path, created_sprint, last_updated_sprint."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.record("proj-1", "frontend/App.tsx", sprint_number=2)

            entry = reg.get("proj-1", "frontend/App.tsx")
            assert entry["path"] == "frontend/App.tsx"
            assert entry["created_sprint"] == 2
            assert entry["last_updated_sprint"] == 2

    def test_workspace_failure_is_nonfatal(self):
        """record() must succeed even when load_project_json raises."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td), raises=True)
            reg.record("proj-1", "backend/main.py", sprint_number=1)

            entry = reg.get("proj-1", "backend/main.py")
            assert entry is not None
            assert entry["requirement_version_id"] is None


# ---------------------------------------------------------------------------
# record() — update existing file
# ---------------------------------------------------------------------------

class TestRecordUpdate:

    def test_update_refreshes_version_id(self):
        """Re-registering an existing file must update requirement_version_id to current."""
        with tempfile.TemporaryDirectory() as td:
            ws = _make_workspace(Path(td), version_id=_VID)
            reg = FileRegistry(workspace_manager=ws)

            reg.record("proj-1", "backend/models/user.py", sprint_number=1)

            # Simulate requirement change → new version
            ws.load_project_json.return_value = {"current_requirement_version_id": _VID2}
            reg.record("proj-1", "backend/models/user.py", sprint_number=2)

            entry = reg.get("proj-1", "backend/models/user.py")
            assert entry["requirement_version_id"] == _VID2

    def test_update_preserves_created_sprint(self):
        """Updating a file must not overwrite created_sprint."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.record("proj-1", "backend/models/user.py", sprint_number=1)
            reg.record("proj-1", "backend/models/user.py", sprint_number=2)

            entry = reg.get("proj-1", "backend/models/user.py")
            assert entry["created_sprint"] == 1
            assert entry["last_updated_sprint"] == 2

    def test_update_does_not_corrupt_other_files(self):
        """Updating file A must not affect file B's entry."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.record("proj-1", "backend/a.py", sprint_number=1)
            reg.record("proj-1", "backend/b.py", sprint_number=1)
            reg.record("proj-1", "backend/a.py", sprint_number=2)

            b_entry = reg.get("proj-1", "backend/b.py")
            assert b_entry["created_sprint"] == 1
            assert b_entry["last_updated_sprint"] == 1


# ---------------------------------------------------------------------------
# record_many()
# ---------------------------------------------------------------------------

class TestRecordMany:

    def test_record_many_stamps_all_entries(self):
        """record_many() must set requirement_version_id on every entry."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            files = ["backend/a.py", "backend/b.py", "frontend/App.tsx"]
            reg.record_many("proj-1", files, sprint_number=1)

            for f in files:
                entry = reg.get("proj-1", f)
                assert entry is not None, f"Entry missing for {f}"
                assert entry["requirement_version_id"] == _VID, f"Wrong version for {f}"

    def test_record_many_uses_single_version_read(self):
        """record_many() reads load_project_json exactly once for the whole batch."""
        with tempfile.TemporaryDirectory() as td:
            ws = _make_workspace(Path(td))
            reg = FileRegistry(workspace_manager=ws)
            reg.record_many("proj-1", ["a.py", "b.py", "c.py"], sprint_number=1)

            # load_project_json: once for _load() implicit call, once for version read
            # The key point: it must NOT call once per file
            call_count = ws.load_project_json.call_count
            assert call_count <= 2  # _load() and version read — never N per file


# ---------------------------------------------------------------------------
# Backward compatibility — entries without the field
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:

    def test_legacy_entry_loads_without_error(self):
        """Existing registry entries without requirement_version_id must load cleanly."""
        with tempfile.TemporaryDirectory() as td:
            # Write a legacy registry directly (no requirement_version_id)
            artifacts_dir = Path(td) / "artifacts"
            artifacts_dir.mkdir(parents=True)
            legacy = {
                "backend/models/user.py": {
                    "path": "backend/models/user.py",
                    "created_sprint": 1,
                    "last_updated_sprint": 1,
                }
            }
            (artifacts_dir / "file_registry.json").write_text(json.dumps(legacy))

            ws = _make_workspace(Path(td))
            reg = FileRegistry(workspace_manager=ws)

            # Must not raise
            entry = reg.get("proj-1", "backend/models/user.py")
            assert entry is not None
            assert entry["created_sprint"] == 1
            # Field absent → None via .get()
            assert entry.get("requirement_version_id") is None

    def test_legacy_entry_updated_gets_version_id(self):
        """When a legacy entry is updated, requirement_version_id must be stamped."""
        with tempfile.TemporaryDirectory() as td:
            artifacts_dir = Path(td) / "artifacts"
            artifacts_dir.mkdir(parents=True)
            legacy = {
                "backend/models/user.py": {
                    "path": "backend/models/user.py",
                    "created_sprint": 1,
                    "last_updated_sprint": 1,
                    # no requirement_version_id
                }
            }
            (artifacts_dir / "file_registry.json").write_text(json.dumps(legacy))

            ws = _make_workspace(Path(td), version_id=_VID)
            reg = FileRegistry(workspace_manager=ws)
            reg.record("proj-1", "backend/models/user.py", sprint_number=2)

            entry = reg.get("proj-1", "backend/models/user.py")
            assert entry["requirement_version_id"] == _VID
            assert entry["created_sprint"] == 1  # preserved


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:

    def test_version_id_survives_json_roundtrip(self):
        """requirement_version_id must persist through write-then-read cycle."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.record("proj-1", "backend/service.py", sprint_number=1)

            # Raw JSON on disk must contain the field
            raw = _read_registry(Path(td))
            assert raw["backend/service.py"]["requirement_version_id"] == _VID

            # Re-reading via get() must return the same value
            entry = reg.get("proj-1", "backend/service.py")
            assert entry["requirement_version_id"] == _VID

    def test_none_version_id_serialized_as_null(self):
        """None requirement_version_id must be written as JSON null, not omitted."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td), version_id=None)
            reg.record("proj-1", "frontend/index.ts", sprint_number=1)

            raw = _read_registry(Path(td))
            assert "requirement_version_id" in raw["frontend/index.ts"]
            assert raw["frontend/index.ts"]["requirement_version_id"] is None

    def test_list_all_returns_version_id(self):
        """list_all() must include requirement_version_id in each entry."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.record("proj-1", "backend/a.py", sprint_number=1)
            reg.record("proj-1", "backend/b.py", sprint_number=1)

            entries = reg.list_all("proj-1")
            assert len(entries) == 2
            for entry in entries:
                assert "requirement_version_id" in entry
                assert entry["requirement_version_id"] == _VID
