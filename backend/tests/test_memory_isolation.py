"""Tests for per-project KnowledgeMemory isolation via KnowledgeMemoryFactory.

These tests verify three guarantees:

1. Separate projects are isolated — storing a key in project A does not
   make it visible to project B.
2. The factory returns the same instance on repeated calls for the same
   project_id (no duplicate HNSW indexes or SQLite connections).
3. cleanup_project removes the instance from the cache so the next
   get_or_create call opens a fresh (empty) store.

All tests use temporary directories so they never touch the real DATA_DIR
and can run in parallel without interference.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Patch DATA_DIR before importing KnowledgeMemoryFactory so test instances
# are written to a temp directory, never to the real backend/data/.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect KnowledgeMemory's DATA_DIR to a per-test temp directory
    and reset the factory's instance cache between tests."""
    import app.memory.knowledge_memory as km_module  # noqa: PLC0415

    # Point all path resolution at the temp dir.
    monkeypatch.setattr(km_module, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(
        km_module,
        "_DEFAULT_DB_PATH",
        tmp_path / "knowledge.sqlite",
    )
    monkeypatch.setattr(
        km_module,
        "_DEFAULT_INDEX_PATH",
        tmp_path / "knowledge.hnsw",
    )

    # Clear the factory cache so each test starts with no loaded instances.
    with km_module.KnowledgeMemoryFactory._lock:
        km_module.KnowledgeMemoryFactory._instances.clear()

    yield

    # Teardown: close all open instances to release SQLite connections.
    with km_module.KnowledgeMemoryFactory._lock:
        for instance in km_module.KnowledgeMemoryFactory._instances.values():
            try:
                instance.close()
            except Exception:
                pass
        km_module.KnowledgeMemoryFactory._instances.clear()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _factory():
    """Return KnowledgeMemoryFactory after the module has been patched."""
    from app.memory.knowledge_memory import KnowledgeMemoryFactory  # noqa: PLC0415
    return KnowledgeMemoryFactory


# ---------------------------------------------------------------------------
# Test 1: separate projects are isolated
# ---------------------------------------------------------------------------


def test_separate_projects_isolated():
    """Storing a key in project_a must not appear in project_b's store."""
    factory = _factory()

    km_a = factory.get_or_create("project_a")
    km_b = factory.get_or_create("project_b")

    # Store a unique value only in project_a.
    km_a.store(key="shared_key", value="value_only_in_a", category="test")

    # Retrieve via get_by_key — project_b must return None.
    assert km_b.get_by_key("shared_key") is None, (
        "project_b returned a value that was only stored in project_a — "
        "HNSW indexes or SQLite databases are shared between projects."
    )

    # project_a must still have it.
    assert km_a.get_by_key("shared_key") == "value_only_in_a"

    # Semantic search on project_b must return no results.
    results_b = km_b.search("value_only_in_a", top_k=5)
    assert results_b == [], (
        "Semantic search on project_b returned results from project_a — "
        "the HNSW indexes are not isolated."
    )

    # Semantic search on project_a must find the entry.
    results_a = km_a.search("value_only_in_a", top_k=1)
    assert len(results_a) == 1
    assert results_a[0].key == "shared_key"


# ---------------------------------------------------------------------------
# Test 2: factory returns the same instance for the same project_id
# ---------------------------------------------------------------------------


def test_factory_returns_same_instance():
    """get_or_create called twice with the same project_id must return the same object."""
    factory = _factory()

    instance_1 = factory.get_or_create("proj1")
    instance_2 = factory.get_or_create("proj1")

    assert instance_1 is instance_2, (
        "KnowledgeMemoryFactory returned two different instances for the same "
        "project_id — the instance cache is not working correctly."
    )


def test_factory_returns_same_instance_concurrent():
    """Concurrent get_or_create calls for the same project_id must still return the same instance."""
    factory = _factory()
    results: list = []
    errors: list = []

    def worker():
        try:
            results.append(factory.get_or_create("concurrent_proj"))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent get_or_create raised: {errors}"
    assert len(results) == 10
    # All threads must have received the same object.
    first = results[0]
    for r in results[1:]:
        assert r is first, (
            "Concurrent get_or_create returned different instances — "
            "the RLock is not protecting _instances correctly."
        )


# ---------------------------------------------------------------------------
# Test 3: cleanup_project removes the instance so the next call creates a new one
# ---------------------------------------------------------------------------


def test_cleanup_removes_instance():
    """After cleanup_project, get_or_create must return a fresh instance."""
    factory = _factory()

    original = factory.get_or_create("proj1")

    # Write something so the instance isn't empty (cleanup only deletes
    # empty-project directories; the instance itself is always evicted).
    original.store(key="test_key", value="test_value")

    factory.cleanup_project("proj1")

    # proj1 must no longer be in the cache.
    with factory._lock:
        assert "proj1" not in factory._instances, (
            "cleanup_project did not remove the instance from _instances."
        )

    # A subsequent get_or_create must create a brand-new instance.
    new_instance = factory.get_or_create("proj1")
    assert new_instance is not original, (
        "get_or_create returned the same (closed) instance after cleanup_project."
    )


def test_cleanup_removes_empty_project_directory(tmp_path: Path):
    """cleanup_project deletes on-disk files when the project has zero entries."""
    import app.memory.knowledge_memory as km_module  # noqa: PLC0415

    factory = km_module.KnowledgeMemoryFactory

    # get_or_create creates the directory lazily.
    instance = factory.get_or_create("empty_proj")
    project_dir = km_module._DATA_DIR / "projects" / "empty_proj"

    # Directory must exist after first use.
    assert project_dir.exists()

    # cleanup_project on a zero-entry project must remove the directory.
    factory.cleanup_project("empty_proj")

    assert not project_dir.exists(), (
        "cleanup_project did not delete the on-disk directory for an empty project."
    )


def test_cleanup_preserves_non_empty_project_directory():
    """cleanup_project must NOT delete files for a project that has entries."""
    import app.memory.knowledge_memory as km_module  # noqa: PLC0415

    factory = km_module.KnowledgeMemoryFactory

    instance = factory.get_or_create("data_proj")
    instance.store(key="k", value="important data")

    project_dir = km_module._DATA_DIR / "projects" / "data_proj"
    assert project_dir.exists()

    factory.cleanup_project("data_proj")

    # Files must still be on disk — data is never deleted.
    assert project_dir.exists(), (
        "cleanup_project deleted the project directory even though it contained entries."
    )


# ---------------------------------------------------------------------------
# Test 4: archive_inactive moves directories and never deletes
# ---------------------------------------------------------------------------


def test_archive_inactive_moves_old_projects(monkeypatch: pytest.MonkeyPatch):
    """archive_inactive must move project dirs older than the threshold to archive/."""
    import time
    import app.memory.knowledge_memory as km_module  # noqa: PLC0415

    factory = km_module.KnowledgeMemoryFactory
    data_dir = km_module._DATA_DIR

    # Create a project directory and backdate its mtime to 35 days ago.
    old_proj_dir = data_dir / "projects" / "old_proj"
    old_proj_dir.mkdir(parents=True, exist_ok=True)
    old_mtime = time.time() - (35 * 86400)
    import os
    os.utime(old_proj_dir, (old_mtime, old_mtime))

    # Create a fresh project directory (mtime = now).
    fresh_proj_dir = data_dir / "projects" / "fresh_proj"
    fresh_proj_dir.mkdir(parents=True, exist_ok=True)

    archived = factory.archive_inactive(days=30)

    assert "old_proj" in archived, "old_proj should have been archived"
    assert "fresh_proj" not in archived, "fresh_proj is still active and must not be archived"

    # old_proj must have moved to archive/, not deleted.
    archive_dir = data_dir / "archive" / "old_proj"
    assert archive_dir.exists(), "archived project directory not found in archive/"
    assert not old_proj_dir.exists(), "original project directory still exists after archiving"

    # fresh_proj must be untouched.
    assert fresh_proj_dir.exists(), "fresh_proj was unexpectedly removed"
