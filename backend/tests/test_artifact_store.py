"""Unit tests for ArtifactStore and WorkspaceManager.create_sprint_folder.

All tests use pytest's ``tmp_path`` fixture so nothing is written to the
real workspace.  No network calls, no LLM, no external dependencies.

Tested behaviours
-----------------
* write → creates file at correct scoped path
* write → returns the Path that was written
* read → returns dict on hit
* read → returns None on miss
* versioning: write(version=True) on existing file → name_v2.json
* versioning: write(version=True) × 2 → name_v3.json
* versioning: write(version=False) always overwrites base file
* read → always returns latest (highest-versioned) file
* exists → True after write, False before
* list_scope → returns sorted base names, versions collapsed
* scope isolation → artifact in sprint_1 not visible in sprint_2
* create_sprint_folder → directory created, idempotent
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------
from app.workspace.artifact_store import ArtifactStore
from app.workspace.manager import WorkspaceManager


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def store(tmp_path: Path) -> ArtifactStore:
    """ArtifactStore rooted at a temporary directory."""
    return ArtifactStore(workspace_root=tmp_path, project_id="proj-test")


@pytest.fixture()
def manager(tmp_path: Path) -> WorkspaceManager:
    """WorkspaceManager rooted at a temporary directory."""
    return WorkspaceManager(root=tmp_path)


# ===========================================================================
# ArtifactStore — write
# ===========================================================================


class TestWrite:
    def test_write_creates_file(self, store: ArtifactStore, tmp_path: Path) -> None:
        """write() persists the file at the expected path."""
        returned = store.write("project", "domain", {"key": "value"})
        expected = tmp_path / "proj-test" / "artifacts" / "project" / "domain.json"
        assert expected.exists(), "File should be created on disk"
        assert returned == expected

    def test_write_returns_path(self, store: ArtifactStore) -> None:
        path = store.write("release", "deploy_manifest", {"version": "1.0"})
        assert isinstance(path, Path)
        assert path.name == "deploy_manifest.json"

    def test_write_content_is_valid_json(self, store: ArtifactStore, tmp_path: Path) -> None:
        data = {"sprints": [1, 2, 3], "project": "Test"}
        store.write("project", "sprint_plan", data)
        raw = (tmp_path / "proj-test" / "artifacts" / "project" / "sprint_plan.json").read_text(
            encoding="utf-8"
        )
        assert json.loads(raw) == data

    def test_write_overwrites_by_default(self, store: ArtifactStore) -> None:
        """write(version=False) should overwrite the base file."""
        store.write("project", "requirements", {"v": 1})
        store.write("project", "requirements", {"v": 2})
        result = store.read("project", "requirements")
        assert result == {"v": 2}

    def test_write_creates_intermediate_dirs(self, store: ArtifactStore, tmp_path: Path) -> None:
        """scope dir must be auto-created even if it didn't exist."""
        store.write("sprint_5", "tasks", {"items": []})
        assert (tmp_path / "proj-test" / "artifacts" / "sprint_5" / "tasks.json").exists()


# ===========================================================================
# ArtifactStore — versioning
# ===========================================================================


class TestVersioning:
    def test_first_write_with_version_true_creates_base(self, store: ArtifactStore) -> None:
        """If base file does not yet exist, version=True still writes base."""
        path = store.write("project", "user_stories", {"v": 1}, version=True)
        assert path.name == "user_stories.json"

    def test_second_write_with_version_true_creates_v2(self, store: ArtifactStore, tmp_path: Path) -> None:
        store.write("project", "user_stories", {"v": 1})
        v2_path = store.write("project", "user_stories", {"v": 2}, version=True)
        assert v2_path.name == "user_stories_v2.json"
        assert (tmp_path / "proj-test" / "artifacts" / "project" / "user_stories_v2.json").exists()

    def test_third_write_with_version_true_creates_v3(self, store: ArtifactStore) -> None:
        store.write("project", "architecture", {"v": 1})
        store.write("project", "architecture", {"v": 2}, version=True)
        v3_path = store.write("project", "architecture", {"v": 3}, version=True)
        assert v3_path.name == "architecture_v3.json"

    def test_base_file_preserved_after_versioning(self, store: ArtifactStore, tmp_path: Path) -> None:
        """The original base file must not be deleted when v2/v3 are written."""
        store.write("project", "user_stories", {"v": 1})
        store.write("project", "user_stories", {"v": 2}, version=True)
        base = tmp_path / "proj-test" / "artifacts" / "project" / "user_stories.json"
        assert base.exists()
        assert json.loads(base.read_text())["v"] == 1

    def test_read_returns_latest_version(self, store: ArtifactStore) -> None:
        """read() must always return the highest-versioned data."""
        store.write("project", "architecture", {"v": 1})
        store.write("project", "architecture", {"v": 2}, version=True)
        store.write("project", "architecture", {"v": 3}, version=True)
        result = store.read("project", "architecture")
        assert result == {"v": 3}

    def test_version_false_does_not_create_v2(self, store: ArtifactStore, tmp_path: Path) -> None:
        store.write("project", "domain", {"x": 1})
        store.write("project", "domain", {"x": 2}, version=False)
        scope_dir = tmp_path / "proj-test" / "artifacts" / "project"
        v2_files = list(scope_dir.glob("domain_v*.json"))
        assert v2_files == [], "No versioned files should exist when version=False"


# ===========================================================================
# ArtifactStore — read
# ===========================================================================


class TestRead:
    def test_read_returns_dict_on_hit(self, store: ArtifactStore) -> None:
        store.write("sprint_1", "tasks", {"sprint": 1, "items": ["a", "b"]})
        result = store.read("sprint_1", "tasks")
        assert result == {"sprint": 1, "items": ["a", "b"]}

    def test_read_returns_none_on_miss(self, store: ArtifactStore) -> None:
        result = store.read("sprint_1", "nonexistent_artifact")
        assert result is None

    def test_read_missing_scope_returns_none(self, store: ArtifactStore) -> None:
        result = store.read("sprint_99", "tasks")
        assert result is None

    def test_read_unicode_content_roundtrip(self, store: ArtifactStore) -> None:
        data = {"name": "Héllo Wörld 日本語", "emoji": "🚀"}
        store.write("release", "unicode_test", data)
        assert store.read("release", "unicode_test") == data


# ===========================================================================
# ArtifactStore — exists
# ===========================================================================


class TestExists:
    def test_exists_false_before_write(self, store: ArtifactStore) -> None:
        assert store.exists("project", "domain") is False

    def test_exists_true_after_write(self, store: ArtifactStore) -> None:
        store.write("project", "domain", {})
        assert store.exists("project", "domain") is True

    def test_exists_true_when_only_versioned_file_present(
        self, store: ArtifactStore, tmp_path: Path
    ) -> None:
        """exists() should detect versioned files even if base is absent."""
        # Manually plant a v2 file without a base file to simulate edge case.
        scope_dir = tmp_path / "proj-test" / "artifacts" / "project"
        scope_dir.mkdir(parents=True, exist_ok=True)
        (scope_dir / "user_stories_v2.json").write_text('{"v": 2}', encoding="utf-8")
        assert store.exists("project", "user_stories") is True

    def test_exists_false_different_scope(self, store: ArtifactStore) -> None:
        store.write("sprint_1", "tasks", {})
        assert store.exists("sprint_2", "tasks") is False


# ===========================================================================
# ArtifactStore — list_scope
# ===========================================================================


class TestListScope:
    def test_list_scope_empty_returns_empty_list(self, store: ArtifactStore) -> None:
        assert store.list_scope("sprint_99") == []

    def test_list_scope_returns_written_names(self, store: ArtifactStore) -> None:
        store.write("sprint_1", "tasks", {})
        store.write("sprint_1", "qa_findings", {})
        result = store.list_scope("sprint_1")
        assert sorted(result) == ["qa_findings", "tasks"]

    def test_list_scope_collapses_versions(self, store: ArtifactStore) -> None:
        """user_stories + user_stories_v2 should appear as a single 'user_stories' entry."""
        store.write("project", "user_stories", {"v": 1})
        store.write("project", "user_stories", {"v": 2}, version=True)
        result = store.list_scope("project")
        assert result.count("user_stories") == 1

    def test_list_scope_sorted(self, store: ArtifactStore) -> None:
        store.write("project", "zzz", {})
        store.write("project", "aaa", {})
        store.write("project", "mmm", {})
        result = store.list_scope("project")
        assert result == sorted(result)


# ===========================================================================
# Scope isolation
# ===========================================================================


class TestScopeIsolation:
    def test_sprint_scopes_are_isolated(self, store: ArtifactStore) -> None:
        store.write("sprint_1", "tasks", {"sprint": 1})
        store.write("sprint_2", "tasks", {"sprint": 2})
        assert store.read("sprint_1", "tasks") == {"sprint": 1}
        assert store.read("sprint_2", "tasks") == {"sprint": 2}

    def test_project_scope_isolated_from_sprints(self, store: ArtifactStore) -> None:
        store.write("project", "architecture", {"source": "project"})
        store.write("sprint_1", "architecture", {"source": "sprint"})
        assert store.read("project", "architecture") == {"source": "project"}
        assert store.read("sprint_1", "architecture") == {"source": "sprint"}

    def test_artifact_in_one_scope_invisible_in_another(self, store: ArtifactStore) -> None:
        store.write("release", "deploy_manifest", {"deployed": True})
        assert store.read("project", "deploy_manifest") is None
        assert store.read("sprint_1", "deploy_manifest") is None


# ===========================================================================
# WorkspaceManager — create_sprint_folder
# ===========================================================================


class TestCreateSprintFolder:
    def test_creates_directory(self, manager: WorkspaceManager, tmp_path: Path) -> None:
        manager.create_sprint_folder("proj-abc", sprint_number=1)
        expected = tmp_path / "proj-abc" / "artifacts" / "sprint_1"
        assert expected.is_dir()

    def test_returns_path(self, manager: WorkspaceManager, tmp_path: Path) -> None:
        path = manager.create_sprint_folder("proj-abc", sprint_number=2)
        assert path == tmp_path / "proj-abc" / "artifacts" / "sprint_2"

    def test_idempotent(self, manager: WorkspaceManager, tmp_path: Path) -> None:
        """Calling twice must not raise and directory must still exist."""
        manager.create_sprint_folder("proj-abc", sprint_number=3)
        manager.create_sprint_folder("proj-abc", sprint_number=3)  # no exception
        assert (tmp_path / "proj-abc" / "artifacts" / "sprint_3").is_dir()

    def test_multiple_sprints_independent(self, manager: WorkspaceManager, tmp_path: Path) -> None:
        for n in range(1, 5):
            manager.create_sprint_folder("proj-multi", sprint_number=n)
        for n in range(1, 5):
            assert (tmp_path / "proj-multi" / "artifacts" / f"sprint_{n}").is_dir()

    def test_creates_intermediate_dirs(self, manager: WorkspaceManager, tmp_path: Path) -> None:
        """Parent artifacts/ dir need not exist beforehand."""
        manager.create_sprint_folder("brand-new-project", sprint_number=1)
        assert (tmp_path / "brand-new-project" / "artifacts" / "sprint_1").is_dir()
