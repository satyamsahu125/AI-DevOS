"""test_phase8_file_registry.py — P8-6 FileRegistry requirements and Sprint 1->2 sanity flow tests.

Covers:
  - register() API and record() compatibility
  - get_existing(project_id, area) project isolation & area filtering
  - get_sprint_files(project_id, sprint) sprint filtering & operations
  - was_written_in_sprint(project_id, area, path, sprint) exact match & negative cases
  - Path normalization (Windows vs POSIX separators)
  - Duplicate registration & operation updates
  - Serialization round-trip
  - Sprint 1 -> Sprint 2 create/update/patch safety sanity flow
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.workspace.file_registry import FileRegistry
from app.workspace.manager import WorkspaceManager
from app.workspace.project_files import ProjectFileManager


def _make_workspace(root: Path) -> WorkspaceManager:
    return WorkspaceManager(root=root)


def _make_registry(root: Path) -> FileRegistry:
    ws = _make_workspace(root)
    return FileRegistry(workspace_manager=ws)


class TestFileRegistryP86:

    def test_01_register_creates_entry(self):
        """register() creates a valid registry entry."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/models/user.py", sprint_number=1, area="backend", operation="create")

            entry = reg.get("proj-1", "backend/models/user.py")
            assert entry is not None
            assert entry["path"] == "backend/models/user.py"
            assert entry["area"] == "backend"
            assert entry["created_sprint"] == 1
            assert entry["last_updated_sprint"] == 1
            assert entry["operation"] == "create"
            assert entry["sprint_history"] == [1]

    def test_02_record_register_compatibility(self):
        """record() and register() are fully compatible."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.record("proj-1", "backend/api/auth.py", sprint_number=1)

            entry = reg.get("proj-1", "backend/api/auth.py")
            assert entry is not None
            assert entry["created_sprint"] == 1

            reg.register("proj-1", "backend/api/auth.py", sprint_number=2, operation="update")
            entry2 = reg.get("proj-1", "backend/api/auth.py")
            assert entry2["created_sprint"] == 1
            assert entry2["last_updated_sprint"] == 2
            assert entry2["operation"] == "update"
            assert entry2["sprint_history"] == [1, 2]

    def test_03_get_existing_returns_only_requested_project(self):
        """get_existing() isolates files by project."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-A", "backend/service.py", sprint_number=1, area="backend")
            reg.register("proj-B", "backend/service.py", sprint_number=1, area="backend")

            a_files = reg.get_existing("proj-A", "backend")
            b_files = reg.get_existing("proj-B", "backend")

            assert len(a_files) == 1
            assert len(b_files) == 1
            assert a_files[0]["path"] == "backend/service.py"

    def test_04_get_existing_filters_by_area(self):
        """get_existing() filters by area."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/models/user.py", sprint_number=1, area="backend")
            reg.register("proj-1", "frontend/src/App.tsx", sprint_number=1, area="frontend")

            be_files = reg.get_existing("proj-1", "backend")
            fe_files = reg.get_existing("proj-1", "frontend")

            assert len(be_files) == 1
            assert be_files[0]["path"] == "backend/models/user.py"
            assert len(fe_files) == 1
            assert fe_files[0]["path"] == "frontend/src/App.tsx"

    def test_05_get_existing_does_not_leak_other_projects(self):
        """get_existing() on an empty project returns empty list without leakage."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-A", "backend/models/user.py", sprint_number=1, area="backend")

            empty_files = reg.get_existing("proj-B", "backend")
            assert empty_files == []

    def test_06_get_sprint_files_returns_only_requested_project(self):
        """get_sprint_files() isolates by project."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-A", "backend/a.py", sprint_number=1)
            reg.register("proj-B", "backend/b.py", sprint_number=1)

            files_a = reg.get_sprint_files("proj-A", 1)
            assert len(files_a) == 1
            assert files_a[0]["path"] == "backend/a.py"

    def test_07_get_sprint_files_filters_exact_sprint(self):
        """get_sprint_files() returns only files for the given sprint."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/s1.py", sprint_number=1)
            reg.register("proj-1", "backend/s2.py", sprint_number=2)

            s1 = reg.get_sprint_files("proj-1", 1)
            s2 = reg.get_sprint_files("proj-1", 2)

            assert len(s1) == 1
            assert s1[0]["path"] == "backend/s1.py"
            assert len(s2) == 1
            assert s2[0]["path"] == "backend/s2.py"

    def test_08_get_sprint_files_handles_multiple_files(self):
        """get_sprint_files() handles multiple files written in the same sprint."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/z.py", sprint_number=1)
            reg.register("proj-1", "backend/a.py", sprint_number=1)

            files = reg.get_sprint_files("proj-1", 1)
            assert len(files) == 2
            # Deterministic sorting
            assert [f["path"] for f in files] == ["backend/a.py", "backend/z.py"]

    def test_09_was_written_in_sprint_exact_match(self):
        """was_written_in_sprint() returns True for exact match."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/models/user.py", sprint_number=1, area="backend")

            assert reg.was_written_in_sprint("proj-1", "backend", "backend/models/user.py", 1) is True
            assert reg.was_written_in_sprint("proj-1", "backend", "models/user.py", 1) is True

    def test_10_was_written_in_sprint_wrong_project(self):
        """was_written_in_sprint() returns False for wrong project."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/models/user.py", sprint_number=1, area="backend")

            assert reg.was_written_in_sprint("proj-2", "backend", "models/user.py", 1) is False

    def test_11_was_written_in_sprint_wrong_area(self):
        """was_written_in_sprint() returns False for wrong area."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/models/user.py", sprint_number=1, area="backend")

            assert reg.was_written_in_sprint("proj-1", "frontend", "models/user.py", 1) is False

    def test_12_was_written_in_sprint_wrong_path(self):
        """was_written_in_sprint() returns False for wrong path."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/models/user.py", sprint_number=1, area="backend")

            assert reg.was_written_in_sprint("proj-1", "backend", "models/order.py", 1) is False

    def test_13_was_written_in_sprint_wrong_sprint(self):
        """was_written_in_sprint() returns False for wrong sprint."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/models/user.py", sprint_number=1, area="backend")

            assert reg.was_written_in_sprint("proj-1", "backend", "models/user.py", 2) is False

    def test_14_path_separator_normalization(self):
        """Windows slashes and POSIX slashes normalize identically."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend\\models\\user.py", sprint_number=1, area="backend")

            assert reg.exists("proj-1", "backend/models/user.py") is True
            assert reg.was_written_in_sprint("proj-1", "backend", "backend\\models\\user.py", 1) is True

    def test_15_duplicate_registration_deterministic(self):
        """Duplicate registration in same sprint or new sprint behaves deterministically."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/a.py", sprint_number=1, operation="create")
            reg.register("proj-1", "backend/a.py", sprint_number=1, operation="create")

            entry = reg.get("proj-1", "backend/a.py")
            assert entry["created_sprint"] == 1
            assert entry["last_updated_sprint"] == 1
            assert entry["sprint_history"] == [1]

            reg.register("proj-1", "backend/a.py", sprint_number=2, operation="update")
            entry2 = reg.get("proj-1", "backend/a.py")
            assert entry2["created_sprint"] == 1
            assert entry2["last_updated_sprint"] == 2
            assert entry2["sprint_history"] == [1, 2]

    def test_16_create_update_patch_operations_distinguishable(self):
        """Operations (create, update, patch) are preserved in entries."""
        with tempfile.TemporaryDirectory() as td:
            reg = _make_registry(Path(td))
            reg.register("proj-1", "backend/c.py", sprint_number=1, operation="create")
            reg.register("proj-1", "backend/u.py", sprint_number=2, operation="update")
            reg.register("proj-1", "backend/p.py", sprint_number=2, operation="patch")

            assert reg.get("proj-1", "backend/c.py")["operation"] == "create"
            assert reg.get("proj-1", "backend/u.py")["operation"] == "update"
            assert reg.get("proj-1", "backend/p.py")["operation"] == "patch"

    def test_17_serialization_round_trip(self):
        """FileRegistry serializes to JSON and reloads cleanly."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reg = _make_registry(root)
            reg.register("proj-1", "backend/app.py", sprint_number=1, area="backend", operation="create")

            reg2 = _make_registry(root)
            entry = reg2.get("proj-1", "backend/app.py")
            assert entry is not None
            assert entry["path"] == "backend/app.py"
            assert entry["area"] == "backend"
            assert entry["created_sprint"] == 1
            assert entry["operation"] == "create"


class TestSprint1To2SanityFlow:
    """Empirically verifies Sprint 1 -> Sprint 2 create/update/patch safety flow."""

    def test_sprint_1_to_2_workflow_sanity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ws = _make_workspace(root)
            reg = FileRegistry(workspace_manager=ws)
            pfm = ProjectFileManager(workspace_manager=ws)

            # Sprint 1: Create file
            reg.register("proj-1", "backend/models/user.py", sprint_number=1, area="backend", operation="create")
            pfm.write_file("proj-1", "backend", "models/user.py", "class User:\n    pass\n", write_mode="create")

            # Verify Sprint 1 registry
            assert reg.exists("proj-1", "backend/models/user.py") is True
            assert reg.was_written_in_sprint("proj-1", "backend", "models/user.py", 1) is True

            # Sprint 2: Existing file detected
            existing = reg.get_existing("proj-1", "backend")
            assert len(existing) == 1
            assert existing[0]["path"] == "backend/models/user.py"

            # Create mode cannot overwrite existing file
            res_create = pfm.write_file("proj-1", "backend", "models/user.py", "BLANK REPLACEMENT", write_mode="create")
            assert res_create.bytes_written == 0
            assert pfm.read_file("proj-1", "backend", "models/user.py") == "class User:\n    pass\n"

            # Update/patch can write resulting content
            updated_code = "class User:\n    id: int\n"
            res_update = pfm.write_file("proj-1", "backend", "models/user.py", updated_code, write_mode="overwrite")
            assert res_update.bytes_written > 0
            assert pfm.read_file("proj-1", "backend", "models/user.py") == updated_code

            # Record Sprint 2 update
            reg.register("proj-1", "backend/models/user.py", sprint_number=2, area="backend", operation="update")
            assert reg.was_written_in_sprint("proj-1", "backend", "models/user.py", 2) is True

            # Verify Project Isolation
            assert reg.get_existing("proj-2", "backend") == []
            assert reg.was_written_in_sprint("proj-2", "backend", "models/user.py", 1) is False
