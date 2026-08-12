"""test_artifact_stamping.py — requirement_version_id stamping in ArtifactManager.

Verifies that:
  1. save_artifact() stamps the current requirement_version_id from project.json.
  2. When no version exists in project.json, the field is None (not an error).
  3. get_artifact() round-trips the field correctly.
  4. _row_to_artifact() reads the field from JSON (used by list_artifacts / get_artifact_history).
  5. Existing serialization is unaffected (no other fields removed/renamed).
  6. workspace_manager failure during version read is non-fatal.

Running:
    cd backend
    python -m pytest tests/test_artifact_stamping.py -v
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.artifact.manager import ArtifactManager
from app.shared.enums.stage import Stage
from app.shared.models.stage_artifact import StageArtifact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VERSION_ID = "req-version-uuid-1234"
_PROJECT_ID = "proj-stamp-test"
_STAGE = Stage.ProductOwner


def _make_manager(
    version_id: str | None = _VERSION_ID,
    workspace_root: Path | None = None,
    load_raises: bool = False,
) -> ArtifactManager:
    """Build ArtifactManager with a mock workspace_manager.

    workspace_root: the temp dir that get_workspace_path returns.
    version_id: what load_project_json returns as current_requirement_version_id.
    load_raises: if True, load_project_json raises an exception (non-fatal test).
    """
    wm = MagicMock()

    if workspace_root is None:
        workspace_root = Path(tempfile.mkdtemp())

    wm.get_workspace_path.return_value = workspace_root

    if load_raises:
        wm.load_project_json.side_effect = RuntimeError("disk failure")
    else:
        pj: dict = {}
        if version_id is not None:
            pj["current_requirement_version_id"] = version_id
        wm.load_project_json.return_value = pj

    db_path = workspace_root / "test_artifacts.db"
    manager = ArtifactManager(
        storage_dir=workspace_root / "legacy",
        workspace_manager=wm,
        db_path=db_path,
    )
    return manager


# ---------------------------------------------------------------------------
# StageArtifact model
# ---------------------------------------------------------------------------

class TestStageArtifactModel:

    def test_default_requirement_version_id_is_none(self):
        """New StageArtifact instances must have requirement_version_id=None by default."""
        artifact = StageArtifact(artifact_id="x", name="test", content="hello")
        assert artifact.requirement_version_id is None

    def test_explicit_requirement_version_id(self):
        """requirement_version_id can be set explicitly."""
        artifact = StageArtifact(
            artifact_id="x", name="test", content="hello",
            requirement_version_id="v-abc-123",
        )
        assert artifact.requirement_version_id == "v-abc-123"

    def test_other_fields_unaffected(self):
        """Adding requirement_version_id must not disturb existing fields."""
        artifact = StageArtifact(
            artifact_id="id1", name="ProductOwner", content="spec",
            project_id="proj-1", attempt=3,
        )
        assert artifact.artifact_id == "id1"
        assert artifact.name == "ProductOwner"
        assert artifact.content == "spec"
        assert artifact.project_id == "proj-1"
        assert artifact.attempt == 3


# ---------------------------------------------------------------------------
# save_artifact() stamping
# ---------------------------------------------------------------------------

class TestSaveArtifactStamping:

    def test_version_id_stamped_in_returned_artifact(self):
        """save_artifact() must set requirement_version_id on the returned StageArtifact."""
        with tempfile.TemporaryDirectory() as td:
            manager = _make_manager(version_id=_VERSION_ID, workspace_root=Path(td))
            try:
                artifact = manager.save_artifact(_PROJECT_ID, _STAGE, "output text")
                assert artifact.requirement_version_id == _VERSION_ID
            finally:
                manager.close()

    def test_version_id_stamped_in_json_file(self):
        """The .json file written by save_artifact() must contain requirement_version_id."""
        with tempfile.TemporaryDirectory() as td:
            manager = _make_manager(version_id=_VERSION_ID, workspace_root=Path(td))
            try:
                manager.save_artifact(_PROJECT_ID, _STAGE, "output text")
                json_path = Path(td) / "artifacts" / f"{_STAGE.value}.json"
                data = json.loads(json_path.read_text())
                assert data["requirement_version_id"] == _VERSION_ID
            finally:
                manager.close()

    def test_no_version_in_project_json_gives_none(self):
        """When project.json has no current_requirement_version_id, field must be None."""
        with tempfile.TemporaryDirectory() as td:
            manager = _make_manager(version_id=None, workspace_root=Path(td))
            try:
                artifact = manager.save_artifact(_PROJECT_ID, _STAGE, "output")
                assert artifact.requirement_version_id is None
            finally:
                manager.close()

    def test_no_version_json_field_is_null(self):
        """When no version exists, the JSON file must contain null for the field."""
        with tempfile.TemporaryDirectory() as td:
            manager = _make_manager(version_id=None, workspace_root=Path(td))
            try:
                manager.save_artifact(_PROJECT_ID, _STAGE, "output")
                json_path = Path(td) / "artifacts" / f"{_STAGE.value}.json"
                data = json.loads(json_path.read_text())
                assert "requirement_version_id" in data
                assert data["requirement_version_id"] is None
            finally:
                manager.close()

    def test_workspace_failure_is_nonfatal(self):
        """If workspace_manager.load_project_json raises, save_artifact must still succeed."""
        with tempfile.TemporaryDirectory() as td:
            manager = _make_manager(load_raises=True, workspace_root=Path(td))
            try:
                artifact = manager.save_artifact(_PROJECT_ID, _STAGE, "output")
                assert artifact.requirement_version_id is None
                assert artifact.content == "output"
            finally:
                manager.close()

    def test_existing_fields_still_present(self):
        """save_artifact() must still write all pre-existing fields to JSON."""
        with tempfile.TemporaryDirectory() as td:
            manager = _make_manager(version_id=_VERSION_ID, workspace_root=Path(td))
            try:
                manager.save_artifact(_PROJECT_ID, _STAGE, "hello", structured_content={"key": "val"}, attempt=2)
                json_path = Path(td) / "artifacts" / f"{_STAGE.value}.json"
                data = json.loads(json_path.read_text())
                assert data["project_id"] == _PROJECT_ID
                assert data["stage"] == _STAGE.value
                assert data["content"] == "hello"
                assert data["structured"] == {"key": "val"}
                assert data["attempt"] == 2
                assert "generated_at" in data
            finally:
                manager.close()


# ---------------------------------------------------------------------------
# get_artifact() round-trip
# ---------------------------------------------------------------------------

class TestGetArtifactRoundTrip:

    def test_get_artifact_returns_version_id(self):
        """get_artifact() must populate requirement_version_id from the JSON file."""
        with tempfile.TemporaryDirectory() as td:
            manager = _make_manager(version_id=_VERSION_ID, workspace_root=Path(td))
            try:
                manager.save_artifact(_PROJECT_ID, _STAGE, "spec output", attempt=1)
                loaded = manager.get_artifact(_PROJECT_ID, _STAGE)
                assert loaded is not None
                assert loaded.requirement_version_id == _VERSION_ID
            finally:
                manager.close()

    def test_get_artifact_missing_field_returns_none(self):
        """Existing JSON files without requirement_version_id must deserialize to None."""
        with tempfile.TemporaryDirectory() as td:
            # Write a legacy-style JSON without the field
            artifacts_dir = Path(td) / "artifacts"
            artifacts_dir.mkdir(parents=True)
            legacy_body = {
                "project_id": _PROJECT_ID,
                "stage": _STAGE.value,
                "generated_at": "2025-01-01T00:00:00+00:00",
                "attempt": 1,
                "content": "legacy content",
                "structured": {},
                # NO requirement_version_id field
            }
            (artifacts_dir / f"{_STAGE.value}.json").write_text(json.dumps(legacy_body))

            wm = MagicMock()
            wm.get_workspace_path.return_value = Path(td)
            wm.load_project_json.return_value = {}
            db_path = Path(td) / "legacy.db"
            manager = ArtifactManager(
                storage_dir=Path(td) / "legacy",
                workspace_manager=wm,
                db_path=db_path,
            )
            try:
                loaded = manager.get_artifact(_PROJECT_ID, _STAGE)
                assert loaded is not None
                assert loaded.requirement_version_id is None
            finally:
                manager.close()


# ---------------------------------------------------------------------------
# _row_to_artifact() (used by list_artifacts / get_artifact_history)
# ---------------------------------------------------------------------------

class TestRowToArtifactStamping:

    def test_row_to_artifact_reads_version_id(self):
        """_row_to_artifact() must read requirement_version_id from the JSON file."""
        with tempfile.TemporaryDirectory() as td:
            manager = _make_manager(version_id=_VERSION_ID, workspace_root=Path(td))
            try:
                manager.save_artifact(_PROJECT_ID, _STAGE, "content", attempt=1)

                json_path = Path(td) / "artifacts" / f"{_STAGE.value}.json"
                md_path = Path(td) / "artifacts" / f"{_STAGE.value}.md"

                artifact = manager._row_to_artifact(_PROJECT_ID, _STAGE.value, str(md_path), str(json_path), 1)
                assert artifact.requirement_version_id == _VERSION_ID
            finally:
                manager.close()

    def test_row_to_artifact_missing_field_returns_none(self):
        """_row_to_artifact() with a legacy JSON file (no field) must return None."""
        with tempfile.TemporaryDirectory() as td:
            artifacts_dir = Path(td) / "artifacts"
            artifacts_dir.mkdir(parents=True)
            legacy = {"content": "old", "structured": {}}
            json_path = artifacts_dir / f"{_STAGE.value}.json"
            json_path.write_text(json.dumps(legacy))
            md_path = artifacts_dir / f"{_STAGE.value}.md"
            md_path.write_text("# legacy")

            wm = MagicMock()
            wm.get_workspace_path.return_value = Path(td)
            wm.load_project_json.return_value = {}
            db_path = Path(td) / "row_test.db"
            manager = ArtifactManager(
                storage_dir=Path(td) / "legacy",
                workspace_manager=wm,
                db_path=db_path,
            )
            try:
                artifact = manager._row_to_artifact(_PROJECT_ID, _STAGE.value, str(md_path), str(json_path), 1)
                assert artifact.requirement_version_id is None
            finally:
                manager.close()
