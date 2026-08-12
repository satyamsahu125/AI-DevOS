"""Initial baseline — all AI DevOS database schemas.

Revision ID: 0001
Revises:     (none — first migration)
Create Date: 2026-08-11

This migration documents and creates the schema for every AI DevOS SQLite
database. Run with AIDEVOS_MIGRATE_DB set to the target database:

    cd backend/

    alembic upgrade head                             # memory.sqlite (default)
    AIDEVOS_MIGRATE_DB=costs     alembic upgrade head
    AIDEVOS_MIGRATE_DB=auth      alembic upgrade head
    AIDEVOS_MIGRATE_DB=knowledge alembic upgrade head
    AIDEVOS_MIGRATE_DB=learning  alembic upgrade head
    AIDEVOS_MIGRATE_DB=lessons   alembic upgrade head
    AIDEVOS_MIGRATE_DB=fileindex alembic upgrade head

All DDL uses CREATE TABLE / INDEX IF NOT EXISTS so this migration is safe
to run against databases that were already created by the application modules
on their first boot.  Use `alembic stamp head` on pre-existing databases to
mark them as current without re-running DDL.

downgrade() is a no-op — dropping production tables requires explicit, human-
approved DBA action, not an automated rollback.

Database → table mapping
------------------------
memory.sqlite   artifacts, safety_checks, project_events, session_checkpoints
                (+ dynamic key-value tables created by sqlite_storage_adapter)
costs.db        llm_calls
auth.db         users, refresh_tokens
knowledge.sqlite knowledge_entries
learning.sqlite  trajectories, templates
lessons.sqlite   lessons
file_index.db    file_index
"""
from __future__ import annotations

import os

from alembic import op

# ---------------------------------------------------------------------------
# Revision metadata
# ---------------------------------------------------------------------------

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_db() -> str:
    """Return the AIDEVOS_MIGRATE_DB selection (same default as env.py)."""
    return os.getenv("AIDEVOS_MIGRATE_DB", "memory")


# ---------------------------------------------------------------------------
# Upgrade (create schemas)
# ---------------------------------------------------------------------------

def upgrade() -> None:
    db = _current_db()
    _UPGRADERS = {
        "memory":    _upgrade_memory,
        "costs":     _upgrade_costs,
        "auth":      _upgrade_auth,
        "knowledge": _upgrade_knowledge,
        "learning":  _upgrade_learning,
        "lessons":   _upgrade_lessons,
        "fileindex": _upgrade_fileindex,
    }
    if db not in _UPGRADERS:
        raise ValueError(f"Unrecognised AIDEVOS_MIGRATE_DB={db!r}")
    _UPGRADERS[db]()


# ---------------------------------------------------------------------------
# Downgrade (intentional no-op)
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Baseline — downgrade is a no-op by design.
    # Dropping tables is a destructive, irreversible operation that must be
    # performed by a DBA with an explicit backup/approval workflow.
    pass


# ---------------------------------------------------------------------------
# Per-database upgrade functions
# ---------------------------------------------------------------------------

def _upgrade_memory() -> None:
    """memory.sqlite — shared database used by multiple subsystems.

    Sources:
      app/artifact/manager.py     → artifacts
      app/execution/safety_policy.py → safety_checks, artifacts (same schema)
      app/memory/project_event_log.py → project_events
      app/session/checkpoint.py   → session_checkpoints

    Note: app/memory/manager.py and app/storage/sqlite_storage_adapter.py
    create additional key-value tables at runtime with dynamic names
    (e.g. "project_state", "agent_output").  Those tables cannot be captured
    in a static migration; they are self-creating via sqlite_storage_adapter.
    """
    # artifacts — written by ArtifactManager; read by SafetyPolicyManager
    # (SafetyPolicyManager creates the same schema independently for its DB
    # connection — they share the same physical file so the second CREATE is
    # harmless via IF NOT EXISTS).
    op.execute("""
        CREATE TABLE IF NOT EXISTS artifacts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT    NOT NULL,
            stage      TEXT    NOT NULL,
            file_path  TEXT    NOT NULL,
            json_path  TEXT    NOT NULL,
            created_at TEXT    NOT NULL,
            attempt    INTEGER NOT NULL,
            approved   INTEGER NOT NULL DEFAULT 0
        )
    """)

    # safety_checks — written by SafetyPolicyManager for audit trail
    op.execute("""
        CREATE TABLE IF NOT EXISTS safety_checks (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            operation  TEXT NOT NULL,
            target     TEXT NOT NULL,
            decision   TEXT NOT NULL,
            reason     TEXT NOT NULL,
            checked_at TEXT NOT NULL
        )
    """)

    # project_events — written by ProjectEventLog for build event history
    op.execute("""
        CREATE TABLE IF NOT EXISTS project_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            stage      TEXT NOT NULL,
            level      TEXT NOT NULL,
            message    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # session_checkpoints — written by CheckpointManager for stage recovery
    op.execute("""
        CREATE TABLE IF NOT EXISTS session_checkpoints (
            session_id            TEXT PRIMARY KEY,
            stage                 TEXT NOT NULL,
            project_id            TEXT NOT NULL,
            attempt_number        INTEGER NOT NULL,
            decisions_made        TEXT NOT NULL,
            remaining_work        TEXT NOT NULL,
            failed_approaches     TEXT NOT NULL,
            last_artifact_summary TEXT NOT NULL,
            saved_at              TEXT NOT NULL
        )
    """)


def _upgrade_costs() -> None:
    """costs.db — LLM call cost tracking (app/llm/cost_tracker.py).

    Note: cost_tracker.py reads the MEMORY_DB_PATH env var but defaults to
    data/costs.db.  This naming inconsistency is a known spec/code mismatch
    in the source; we use the actual default path here.
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_calls (
            call_id           TEXT PRIMARY KEY,
            project_id        TEXT    NOT NULL,
            stage             TEXT    NOT NULL,
            agent             TEXT    DEFAULT '',
            provider          TEXT    NOT NULL,
            model             TEXT    NOT NULL,
            prompt_tokens     INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens      INTEGER DEFAULT 0,
            latency_ms        REAL    DEFAULT 0,
            success           INTEGER DEFAULT 1,
            error             TEXT,
            called_at         TEXT    NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_llm_calls_project
            ON llm_calls(project_id)
    """)


def _upgrade_auth() -> None:
    """auth.db — user accounts and refresh tokens (app/db/users.py)."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              TEXT PRIMARY KEY,
            email           TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            role            TEXT NOT NULL DEFAULT 'developer',
            created_at      TEXT NOT NULL,
            last_login      TEXT
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            token_hash   TEXT PRIMARY KEY,
            user_id      TEXT NOT NULL REFERENCES users(id),
            expires_at   TEXT NOT NULL,
            invalidated  INTEGER NOT NULL DEFAULT 0,
            created_at   TEXT NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user
            ON refresh_tokens(user_id)
    """)


def _upgrade_knowledge() -> None:
    """knowledge.sqlite — semantic knowledge store (app/memory/knowledge_memory.py).

    The companion HNSW index (knowledge.hnsw) is a binary file managed by
    hnswlib and is not tracked by Alembic.
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_entries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            key        TEXT UNIQUE NOT NULL,
            value      TEXT NOT NULL,
            category   TEXT NOT NULL DEFAULT '',
            source     TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)


def _upgrade_learning() -> None:
    """learning.sqlite — trajectory learning and template store.

    Sources:
      app/memory/learning_loop.py  → trajectories
      app/learning/template_engine.py → templates
    """
    # trajectories — outcome records used to train/improve agent behaviour
    # The source adds `project_id` via ALTER TABLE on existing DBs;
    # we include it in the canonical schema so new deployments get it upfront.
    op.execute("""
        CREATE TABLE IF NOT EXISTS trajectories (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id        TEXT    NOT NULL DEFAULT '',
            stage             TEXT    NOT NULL,
            task_description  TEXT    NOT NULL,
            artifact_summary  TEXT    NOT NULL,
            retry_count       INTEGER NOT NULL,
            approved          INTEGER NOT NULL,
            reviewer_feedback TEXT    NOT NULL,
            agent_model       TEXT    NOT NULL,
            tokens_used       INTEGER NOT NULL,
            latency_ms        REAL    NOT NULL,
            recorded_at       TEXT    NOT NULL
        )
    """)

    # templates — successful artifact structures reused across projects
    op.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            template_id       TEXT PRIMARY KEY,
            stage             TEXT NOT NULL,
            structure         TEXT NOT NULL,
            source_project_id TEXT NOT NULL DEFAULT '',
            created_at        TEXT NOT NULL
        )
    """)


def _upgrade_lessons() -> None:
    """lessons.sqlite — post-review lessons captured per project/stage.

    Source: app/memory/lesson_store.py
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS lessons (
            lesson_id                  TEXT PRIMARY KEY,
            stage                      TEXT NOT NULL,
            project_id                 TEXT NOT NULL,
            what_worked                TEXT NOT NULL,
            what_failed                TEXT NOT NULL,
            reviewer_said              TEXT NOT NULL,
            retry_count_when_learned   INTEGER NOT NULL,
            created_at                 TEXT NOT NULL
        )
    """)


def _upgrade_fileindex() -> None:
    """file_index.db — static analysis index of generated project files.

    Source: app/intelligence/file_indexer.py
    The DB path is hardcoded in container.py (data/file_index.db) and is not
    configurable via an env var.
    """
    op.execute("""
        CREATE TABLE IF NOT EXISTS file_index (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id    TEXT    NOT NULL,
            file_path     TEXT    NOT NULL,
            language      TEXT    NOT NULL,
            purpose       TEXT    DEFAULT '',
            classes       TEXT    DEFAULT '[]',
            functions     TEXT    DEFAULT '[]',
            imports       TEXT    DEFAULT '[]',
            exports       TEXT    DEFAULT '[]',
            dependencies  TEXT    DEFAULT '[]',
            line_count    INTEGER DEFAULT 0,
            size_bytes    INTEGER DEFAULT 0,
            sprint_number INTEGER DEFAULT 0,
            last_updated  TEXT    NOT NULL,
            UNIQUE(project_id, file_path)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_file_index_project
            ON file_index(project_id)
    """)
