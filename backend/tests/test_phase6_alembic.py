"""test_phase6_alembic.py — Alembic baseline migration regression tests.

Verifies that every AI DevOS database schema can be created by the baseline
migration without relying on application module boot code.

Running:
    cd backend
    python -m pytest tests/test_phase6_alembic.py -v
"""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import tempfile
import sys
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import pytest
pytest.importorskip("alembic")

# ---------------------------------------------------------------------------
# Migration module loader
# ---------------------------------------------------------------------------

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations" / "versions" / "0001_initial_baseline.py"
)


def _load_migration():
    """Import 0001_initial_baseline.py as a module object."""
    spec = importlib.util.spec_from_file_location("migration_0001", _MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_upgrade_fn(fn_name: str) -> sqlite3.Connection:
    """Execute a single _upgrade_<db>() function against a fresh in-memory DB.

    Returns the sqlite3 connection so callers can inspect the resulting schema.
    """
    mod = _load_migration()
    fn: Callable = getattr(mod, fn_name)

    conn = sqlite3.connect(":memory:")

    import alembic.op as op_module
    orig_execute = op_module.execute

    def _fake_execute(sql, *args, **kwargs):
        # executescript handles multiple statements separated by semicolons
        conn.executescript(str(sql))
        conn.commit()

    op_module.execute = _fake_execute
    try:
        fn()
    finally:
        op_module.execute = orig_execute

    return conn


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _indexes(conn: sqlite3.Connection) -> set[str]:
    return {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

class TestMigrationFileStructure:
    """Verify the Alembic infrastructure files are present and well-formed."""

    def test_alembic_ini_exists(self):
        ini = Path(__file__).resolve().parents[1] / "alembic.ini"
        assert ini.exists(), "alembic.ini not found in backend/"

    def test_migrations_env_exists(self):
        env = Path(__file__).resolve().parents[1] / "migrations" / "env.py"
        assert env.exists(), "migrations/env.py not found"

    def test_migrations_script_mako_exists(self):
        mako = Path(__file__).resolve().parents[1] / "migrations" / "script.py.mako"
        assert mako.exists(), "migrations/script.py.mako not found"

    def test_baseline_migration_exists(self):
        assert _MIGRATION_PATH.exists(), f"Baseline migration not found: {_MIGRATION_PATH}"

    def test_baseline_revision_is_0001(self):
        mod = _load_migration()
        assert mod.revision == "0001", f"Expected revision '0001', got {mod.revision!r}"

    def test_baseline_has_no_down_revision(self):
        mod = _load_migration()
        assert mod.down_revision is None, (
            f"Baseline must have down_revision=None, got {mod.down_revision!r}"
        )

    def test_alembic_in_requirements(self):
        req = Path(__file__).resolve().parents[1] / "requirements.txt"
        content = req.read_text()
        assert "alembic" in content.lower(), "alembic must be in requirements.txt"

    def test_alembic_version_requirement(self):
        req = Path(__file__).resolve().parents[1] / "requirements.txt"
        import re
        match = re.search(r"alembic\s*>=\s*([\d.]+)", req.read_text())
        assert match, "requirements.txt must specify alembic>=<version>"
        major, minor = map(int, match.group(1).split(".")[:2])
        assert (major, minor) >= (1, 13), (
            f"alembic>= version must be >= 1.13, got {match.group(1)}"
        )


# ---------------------------------------------------------------------------
# Schema correctness tests — one class per database
# ---------------------------------------------------------------------------

class TestMemorySchema:
    """memory.sqlite — shared database used by multiple subsystems."""

    def setup_method(self):
        self.conn = _run_upgrade_fn("_upgrade_memory")

    def test_artifacts_table_created(self):
        assert "artifacts" in _tables(self.conn)

    def test_artifacts_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(artifacts)").fetchall()}
        assert {"id", "project_id", "stage", "file_path", "json_path",
                "created_at", "attempt", "approved"} <= cols

    def test_artifacts_approved_default_zero(self):
        self.conn.execute(
            "INSERT INTO artifacts (project_id, stage, file_path, json_path, created_at, attempt) "
            "VALUES ('p1', 'spec', '/tmp/f', '/tmp/j', '2026-01-01', 1)"
        )
        row = self.conn.execute("SELECT approved FROM artifacts").fetchone()
        assert row[0] == 0

    def test_safety_checks_table_created(self):
        assert "safety_checks" in _tables(self.conn)

    def test_safety_checks_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(safety_checks)").fetchall()}
        assert {"id", "operation", "target", "decision", "reason", "checked_at"} <= cols

    def test_project_events_table_created(self):
        assert "project_events" in _tables(self.conn)

    def test_project_events_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(project_events)").fetchall()}
        assert {"id", "project_id", "stage", "level", "message", "created_at"} <= cols

    def test_session_checkpoints_table_created(self):
        assert "session_checkpoints" in _tables(self.conn)

    def test_session_checkpoints_primary_key_is_session_id(self):
        pk_cols = [
            r[1]
            for r in self.conn.execute("PRAGMA table_info(session_checkpoints)").fetchall()
            if r[5] == 1  # pk column
        ]
        assert pk_cols == ["session_id"]

    def test_session_checkpoints_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(session_checkpoints)").fetchall()}
        assert {
            "session_id", "stage", "project_id", "attempt_number",
            "decisions_made", "remaining_work", "failed_approaches",
            "last_artifact_summary", "saved_at",
        } <= cols


class TestCostsSchema:
    """costs.db — LLM call cost tracking."""

    def setup_method(self):
        self.conn = _run_upgrade_fn("_upgrade_costs")

    def test_llm_calls_table_created(self):
        assert "llm_calls" in _tables(self.conn)

    def test_llm_calls_primary_key_is_call_id(self):
        pk_cols = [
            r[1]
            for r in self.conn.execute("PRAGMA table_info(llm_calls)").fetchall()
            if r[5] == 1
        ]
        assert pk_cols == ["call_id"]

    def test_llm_calls_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(llm_calls)").fetchall()}
        assert {
            "call_id", "project_id", "stage", "agent", "provider", "model",
            "prompt_tokens", "completion_tokens", "total_tokens",
            "latency_ms", "success", "error", "called_at",
        } <= cols

    def test_idx_llm_calls_project_created(self):
        assert "idx_llm_calls_project" in _indexes(self.conn)


class TestAuthSchema:
    """auth.db — users and refresh tokens."""

    def setup_method(self):
        self.conn = _run_upgrade_fn("_upgrade_auth")

    def test_users_table_created(self):
        assert "users" in _tables(self.conn)

    def test_users_email_unique(self):
        self.conn.execute(
            "INSERT INTO users (id, email, hashed_password, created_at) "
            "VALUES ('u1', 'a@b.com', 'hash', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO users (id, email, hashed_password, created_at) "
                "VALUES ('u2', 'a@b.com', 'hash', '2026-01-01')"
            )

    def test_refresh_tokens_table_created(self):
        assert "refresh_tokens" in _tables(self.conn)

    def test_refresh_tokens_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(refresh_tokens)").fetchall()}
        assert {"token_hash", "user_id", "expires_at", "invalidated", "created_at"} <= cols

    def test_idx_refresh_tokens_user_created(self):
        assert "idx_refresh_tokens_user" in _indexes(self.conn)


class TestKnowledgeSchema:
    """knowledge.sqlite — semantic knowledge store."""

    def setup_method(self):
        self.conn = _run_upgrade_fn("_upgrade_knowledge")

    def test_knowledge_entries_table_created(self):
        assert "knowledge_entries" in _tables(self.conn)

    def test_knowledge_entries_key_unique(self):
        self.conn.execute(
            "INSERT INTO knowledge_entries (key, value, created_at) "
            "VALUES ('k1', 'v1', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO knowledge_entries (key, value, created_at) "
                "VALUES ('k1', 'v2', '2026-01-01')"
            )

    def test_knowledge_entries_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(knowledge_entries)").fetchall()}
        assert {"id", "key", "value", "category", "source", "created_at"} <= cols


class TestLearningSchema:
    """learning.sqlite — trajectory and template store."""

    def setup_method(self):
        self.conn = _run_upgrade_fn("_upgrade_learning")

    def test_trajectories_table_created(self):
        assert "trajectories" in _tables(self.conn)

    def test_trajectories_includes_project_id(self):
        """project_id column must be present (added via ALTER TABLE in production; new deployments get it upfront)."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(trajectories)").fetchall()}
        assert "project_id" in cols

    def test_trajectories_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(trajectories)").fetchall()}
        assert {
            "id", "project_id", "stage", "task_description", "artifact_summary",
            "retry_count", "approved", "reviewer_feedback", "agent_model",
            "tokens_used", "latency_ms", "recorded_at",
        } <= cols

    def test_templates_table_created(self):
        assert "templates" in _tables(self.conn)

    def test_templates_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(templates)").fetchall()}
        assert {"template_id", "stage", "structure", "source_project_id", "created_at"} <= cols


class TestLessonsSchema:
    """lessons.sqlite — post-review lessons."""

    def setup_method(self):
        self.conn = _run_upgrade_fn("_upgrade_lessons")

    def test_lessons_table_created(self):
        assert "lessons" in _tables(self.conn)

    def test_lessons_primary_key_is_lesson_id(self):
        pk_cols = [
            r[1]
            for r in self.conn.execute("PRAGMA table_info(lessons)").fetchall()
            if r[5] == 1
        ]
        assert pk_cols == ["lesson_id"]

    def test_lessons_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(lessons)").fetchall()}
        assert {
            "lesson_id", "stage", "project_id", "what_worked", "what_failed",
            "reviewer_said", "retry_count_when_learned", "created_at",
        } <= cols


class TestFileIndexSchema:
    """file_index.db — static analysis index."""

    def setup_method(self):
        self.conn = _run_upgrade_fn("_upgrade_fileindex")

    def test_file_index_table_created(self):
        assert "file_index" in _tables(self.conn)

    def test_file_index_unique_constraint(self):
        self.conn.execute(
            "INSERT INTO file_index (project_id, file_path, language, last_updated) "
            "VALUES ('p1', 'src/main.py', 'python', '2026-01-01')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO file_index (project_id, file_path, language, last_updated) "
                "VALUES ('p1', 'src/main.py', 'python', '2026-01-01')"
            )

    def test_file_index_columns(self):
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(file_index)").fetchall()}
        assert {
            "id", "project_id", "file_path", "language", "purpose",
            "classes", "functions", "imports", "exports", "dependencies",
            "line_count", "size_bytes", "sprint_number", "last_updated",
        } <= cols

    def test_idx_file_index_project_created(self):
        assert "idx_file_index_project" in _indexes(self.conn)


# ---------------------------------------------------------------------------
# End-to-end: upgrade() dispatch
# ---------------------------------------------------------------------------

class TestUpgradeDispatch:
    """upgrade() must call the correct per-database function based on AIDEVOS_MIGRATE_DB."""

    def test_upgrade_memory_dispatches_correctly(self, monkeypatch):
        monkeypatch.setenv("AIDEVOS_MIGRATE_DB", "memory")
        mod = _load_migration()
        conn = sqlite3.connect(":memory:")
        import alembic.op as op_module
        orig = op_module.execute
        op_module.execute = lambda sql, *a, **kw: (conn.executescript(str(sql)), conn.commit())
        try:
            mod.upgrade()
        finally:
            op_module.execute = orig
        assert "artifacts" in _tables(conn)
        assert "session_checkpoints" in _tables(conn)

    def test_upgrade_unknown_db_raises(self, monkeypatch):
        monkeypatch.setenv("AIDEVOS_MIGRATE_DB", "nonexistent_db")
        mod = _load_migration()
        with pytest.raises(ValueError, match="nonexistent_db"):
            mod.upgrade()

    def test_downgrade_is_noop(self, monkeypatch):
        """downgrade() must complete without error and without dropping tables."""
        monkeypatch.setenv("AIDEVOS_MIGRATE_DB", "memory")
        mod = _load_migration()
        # Must not raise; must not call op.execute (no DDL)
        import alembic.op as op_module
        calls = []
        orig = op_module.execute
        op_module.execute = lambda sql, *a, **kw: calls.append(sql)
        try:
            mod.downgrade()
        finally:
            op_module.execute = orig
        assert calls == [], f"downgrade() must not execute any SQL, but ran: {calls}"


# ---------------------------------------------------------------------------
# env.py validation
# ---------------------------------------------------------------------------

class TestAlembicEnvModule:
    """Validate env.py database URL resolution without connecting to Alembic internals."""

    def test_env_has_seven_databases(self):
        env_path = Path(__file__).resolve().parents[1] / "migrations" / "env.py"
        content = env_path.read_text()
        for db in ("memory", "costs", "auth", "knowledge", "learning", "lessons", "fileindex"):
            assert f'"{db}"' in content or f"'{db}'" in content, (
                f"env.py must define URL for database '{db}'"
            )

    def test_env_uses_per_db_version_table(self):
        env_path = Path(__file__).resolve().parents[1] / "migrations" / "env.py"
        content = env_path.read_text()
        assert "alembic_version_" in content, (
            "env.py must use per-database version tables (alembic_version_<name>)"
        )

    def test_env_references_correct_env_vars(self):
        env_path = Path(__file__).resolve().parents[1] / "migrations" / "env.py"
        content = env_path.read_text()
        # Must use the same env var names as the application modules
        for env_var in ("MEMORY_DB_PATH", "AUTH_DB_PATH", "KNOWLEDGE_DB", "LEARNING_DB", "LESSONS_DB"):
            assert env_var in content, (
                f"env.py must reference {env_var} (same as the application module)"
            )
