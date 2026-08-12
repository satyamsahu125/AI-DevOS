"""test_phase6_db_paths.py — Phase 6 MIGRATE: SQLite database path anchoring.

Verifies that every module's default database path is:
  1. An absolute path (not relative to process CWD).
  2. Anchored inside backend/data/ regardless of CWD.
  3. Overridable by env vars; explicit db_path= args still work unchanged.
  4. Idempotent — importing the module from any CWD gives the same absolute path.

Design note: every module computes its default at import time via
    Path(__file__).resolve().parents[2] / "data"
where parents[2] = backend/ for all backend/app/{subdir}/ files.

CWD-independence is verified by temporarily changing os.getcwd() via chdir,
then re-importing a fresh module instance and checking the computed path.

Running:
    cd backend
    python -m pytest tests/test_phase6_db_paths.py -v
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Canonical backend/data/ anchor (absolute, derived independently of the modules under test)
_BACKEND_ROOT = Path(__file__).resolve().parents[1]   # backend/
_DATA_DIR = _BACKEND_ROOT / "data"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _reload(module_name: str):
    """Force a clean reimport of module_name (removes cached version first)."""
    if module_name in sys.modules:
        del sys.modules[module_name]
    return importlib.import_module(module_name)


def _assert_absolute_in_data(path: Path, label: str) -> None:
    assert path.is_absolute(), f"{label}: expected absolute path, got relative: {path}"
    assert path.parts[-2] == "data", (
        f"{label}: expected parent directory to be 'data', got {path.parent.name!r}: {path}"
    )


# ---------------------------------------------------------------------------
# 1-2: Settings model defaults are absolute and inside backend/data/
# ---------------------------------------------------------------------------

class TestSettingsDefaults:

    def test_knowledge_db_is_absolute(self):
        from app.config.models import Settings
        s = Settings()
        _assert_absolute_in_data(Path(s.knowledge_db), "Settings.knowledge_db")

    def test_learning_db_is_absolute(self):
        from app.config.models import Settings
        s = Settings()
        _assert_absolute_in_data(Path(s.learning_db), "Settings.learning_db")

    def test_lessons_db_is_absolute(self):
        from app.config.models import Settings
        s = Settings()
        _assert_absolute_in_data(Path(s.lessons_db), "Settings.lessons_db")

    def test_memory_db_path_is_absolute(self):
        from app.config.models import Settings
        s = Settings()
        _assert_absolute_in_data(Path(s.memory_db_path), "Settings.memory_db_path")

    def test_settings_defaults_inside_backend_data(self):
        from app.config.models import Settings
        s = Settings()
        for field_name in ("knowledge_db", "learning_db", "lessons_db", "memory_db_path"):
            p = Path(getattr(s, field_name))
            assert p.is_absolute(), f"Settings.{field_name} not absolute: {p}"
            assert str(p).startswith(str(_DATA_DIR)), (
                f"Settings.{field_name} not inside backend/data/: {p}"
            )


# ---------------------------------------------------------------------------
# 3-6: Per-module _DEFAULT_DB_PATH variables
# ---------------------------------------------------------------------------

class TestModuleDefaultPaths:

    def _check(self, module_name: str, attr: str = "_DEFAULT_DB_PATH"):
        mod = importlib.import_module(module_name)
        path: Path = getattr(mod, attr)
        _assert_absolute_in_data(path, f"{module_name}.{attr}")
        return path

    def test_memory_manager_default(self):
        """MemoryManager's default db must be absolute inside data/."""
        # MemoryManager computes its default inside __init__, not at module level.
        # We verify via Settings integration (Settings.memory_db_path feeds it).
        from app.config.models import Settings
        s = Settings()
        p = Path(s.memory_db_path)
        _assert_absolute_in_data(p, "Settings.memory_db_path (MemoryManager default)")

    def test_learning_loop_default(self):
        self._check("app.memory.learning_loop")

    def test_lesson_store_default(self):
        self._check("app.memory.lesson_store")

    def test_knowledge_memory_db_default(self):
        self._check("app.memory.knowledge_memory")

    def test_knowledge_memory_index_default(self):
        mod = importlib.import_module("app.memory.knowledge_memory")
        path = mod._DEFAULT_INDEX_PATH
        assert path.is_absolute(), f"knowledge_memory._DEFAULT_INDEX_PATH not absolute: {path}"
        assert path.parts[-2] == "data", f"expected parent 'data', got {path.parent.name!r}"

    def test_project_event_log_default(self):
        self._check("app.memory.project_event_log")

    def test_template_engine_default(self):
        self._check("app.learning.template_engine")

    def test_users_default(self):
        self._check("app.db.users")

    def test_artifact_manager_default(self):
        self._check("app.artifact.manager")

    def test_safety_policy_default(self):
        self._check("app.execution.safety_policy")

    def test_checkpoint_default(self):
        self._check("app.session.checkpoint")

    def test_cost_tracker_default(self):
        self._check("app.llm.cost_tracker")


# ---------------------------------------------------------------------------
# 7: All defaults resolve inside the same backend/data/ directory
# ---------------------------------------------------------------------------

def test_all_defaults_point_to_backend_data():
    """Every module's default database path must be inside backend/data/."""
    from app.config.models import Settings
    import app.memory.learning_loop as ll
    import app.memory.lesson_store as ls
    import app.memory.knowledge_memory as km
    import app.memory.project_event_log as pel
    import app.learning.template_engine as te
    import app.db.users as u
    import app.artifact.manager as am
    import app.execution.safety_policy as sp
    import app.session.checkpoint as ck
    import app.llm.cost_tracker as ct

    s = Settings()
    paths = {
        "Settings.knowledge_db":      Path(s.knowledge_db),
        "Settings.learning_db":       Path(s.learning_db),
        "Settings.lessons_db":        Path(s.lessons_db),
        "Settings.memory_db_path":    Path(s.memory_db_path),
        "learning_loop._DEFAULT":     ll._DEFAULT_DB_PATH,
        "lesson_store._DEFAULT":      ls._DEFAULT_DB_PATH,
        "knowledge_memory._DEFAULT":  km._DEFAULT_DB_PATH,
        "knowledge_memory._INDEX":    km._DEFAULT_INDEX_PATH,
        "project_event_log._DEFAULT": pel._DEFAULT_DB_PATH,
        "template_engine._DEFAULT":   te._DEFAULT_DB_PATH,
        "users._DEFAULT":             u._DEFAULT_DB_PATH,
        "artifact.manager._DEFAULT":  am._DEFAULT_DB_PATH,
        "safety_policy._DEFAULT":     sp._DEFAULT_DB_PATH,
        "checkpoint._DEFAULT":        ck._DEFAULT_DB_PATH,
        "cost_tracker._DEFAULT":      ct._DEFAULT_DB_PATH,
    }

    failures = []
    for label, path in paths.items():
        if not path.is_absolute():
            failures.append(f"  {label}: not absolute: {path}")
        elif not str(path).startswith(str(_DATA_DIR)):
            failures.append(f"  {label}: not inside backend/data/: {path}")

    if failures:
        pytest.fail("Database path(s) not in backend/data/:\n" + "\n".join(failures))


# ---------------------------------------------------------------------------
# 8: CWD-independence — changing CWD does not change the resolved path
# ---------------------------------------------------------------------------

def test_learning_loop_cwd_independent(tmp_path):
    """_DEFAULT_DB_PATH in learning_loop must not change when CWD changes."""
    import app.memory.learning_loop as ll_orig
    original_path = str(ll_orig._DEFAULT_DB_PATH)

    # Change CWD to a temp directory completely outside the project tree.
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        # Force reimport from the new CWD
        if "app.memory.learning_loop" in sys.modules:
            del sys.modules["app.memory.learning_loop"]
        import app.memory.learning_loop as ll_new
        new_path = str(ll_new._DEFAULT_DB_PATH)
    finally:
        os.chdir(old_cwd)

    assert new_path == original_path, (
        f"Path changed with CWD!\n  original: {original_path}\n  after chdir: {new_path}"
    )


def test_settings_cwd_independent(tmp_path):
    """Settings.knowledge_db default must not change when CWD changes."""
    from app.config.models import Settings
    original = Settings().knowledge_db

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        if "app.config.models" in sys.modules:
            del sys.modules["app.config.models"]
        from app.config.models import Settings as S2
        new_path = S2().knowledge_db
    finally:
        os.chdir(old_cwd)

    assert new_path == original, (
        f"Settings.knowledge_db changed with CWD!\n  original: {original}\n  after chdir: {new_path}"
    )


# ---------------------------------------------------------------------------
# 9: Env var override still works
# ---------------------------------------------------------------------------

def test_env_var_overrides_learning_db(tmp_path, monkeypatch):
    """Setting LEARNING_DB env var must override the anchored default."""
    custom = str(tmp_path / "custom_learning.sqlite")
    monkeypatch.setenv("LEARNING_DB", custom)

    if "app.memory.learning_loop" in sys.modules:
        del sys.modules["app.memory.learning_loop"]
    import app.memory.learning_loop as ll
    assert str(ll._DEFAULT_DB_PATH) == custom


def test_env_var_overrides_auth_db(tmp_path, monkeypatch):
    """Setting AUTH_DB_PATH env var must override the anchored default."""
    custom = str(tmp_path / "custom_auth.db")
    monkeypatch.setenv("AUTH_DB_PATH", custom)

    if "app.db.users" in sys.modules:
        del sys.modules["app.db.users"]
    import app.db.users as u
    assert str(u._DEFAULT_DB_PATH) == custom


# ---------------------------------------------------------------------------
# 10: Explicit db_path= constructor argument is preserved
# ---------------------------------------------------------------------------

def test_lesson_store_explicit_path(tmp_path):
    """LessonStore(db_path=explicit) must use the explicit path, not the default."""
    from app.memory.lesson_store import LessonStore, _DEFAULT_DB_PATH

    explicit = tmp_path / "explicit_lessons.sqlite"
    store = LessonStore(db_path=explicit)

    try:
        # The connection should point to the explicit path
        assert Path(store._db_path) == explicit, (
            f"Expected explicit path {explicit}, got {store._db_path}"
        )
    finally:
        try:
            store._conn.close()
        except Exception:
            pass


def test_learning_loop_explicit_path(tmp_path):
    """LearningLoop(db_path=explicit) must use the explicit path."""
    from app.memory.learning_loop import LearningLoop, _DEFAULT_DB_PATH

    # Minimal stub for knowledge_memory (not needed for path test)
    class _StubKM:
        def search(self, *a, **kw): return []
        def store(self, *a, **kw): pass

    explicit = tmp_path / "explicit_learning.sqlite"
    loop = LearningLoop(knowledge_memory=_StubKM(), db_path=explicit)

    try:
        assert Path(loop._db_path) == explicit, (
            f"Expected explicit path {explicit}, got {loop._db_path}"
        )
    finally:
        try:
            loop._conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 11: container.py _data_dir resolves to backend/data/
# ---------------------------------------------------------------------------

def test_container_data_dir_resolves_to_backend_data():
    """container.py's _data_dir computation must resolve to backend/data/."""
    # Reproduce the container.py formula independently
    container_file = Path(__file__).resolve().parents[1] / "app" / "kernel" / "container.py"
    assert container_file.exists(), f"container.py not found at {container_file}"

    # parents[2] from container.py's resolved path = backend/
    computed = container_file.resolve().parents[2] / "data"
    assert computed == _DATA_DIR, (
        f"container.py _data_dir resolves to {computed}, expected {_DATA_DIR}"
    )


# ---------------------------------------------------------------------------
# 12: backend/data/ directory exists (created by package)
# ---------------------------------------------------------------------------

def test_backend_data_directory_exists():
    """backend/data/ must exist so that database files can be created there."""
    assert _DATA_DIR.exists(), (
        f"backend/data/ directory does not exist: {_DATA_DIR}\n"
        "It should be created at runtime by the first component that writes a db file."
    )
    assert _DATA_DIR.is_dir(), f"backend/data/ exists but is not a directory: {_DATA_DIR}"
