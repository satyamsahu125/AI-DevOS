"""Alembic migration environment — AI DevOS multi-database support.

All AI DevOS databases are raw SQLite files managed without SQLAlchemy ORM.
Migrations are hand-written SQL executed via op.execute().

Database selection:
    Set AIDEVOS_MIGRATE_DB to one of:
        memory      data/memory.sqlite    (default)
        costs       data/costs.db
        auth        data/auth.db
        knowledge   data/knowledge.sqlite
        learning    data/learning.sqlite
        lessons     data/lessons.sqlite
        fileindex   data/file_index.db

    Each database gets its own alembic_version_<name> tracking table so
    multiple databases can coexist with independent revision histories.

Path resolution:
    Paths follow the same env-var logic as the application modules.
    Alembic is always run from backend/, so relative paths resolve correctly.
"""
from __future__ import annotations

import os
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# ---------------------------------------------------------------------------
# Database URL resolution
# ---------------------------------------------------------------------------

# The backend/ directory — Alembic must be run from here.
_BACKEND = Path(__file__).resolve().parents[1]
_DATA = _BACKEND / "data"


def _sqlite_url(path: str | Path) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = _BACKEND / p
    return f"sqlite:///{p}"


# Mirror the exact env-var names and defaults used by each application module.
# Keep in sync with the modules listed in the inline comments.
_DB_URLS: dict[str, str] = {
    # app/artifact/manager.py, app/execution/safety_policy.py,
    # app/memory/project_event_log.py, app/session/checkpoint.py,
    # app/memory/manager.py (via sqlite_storage_adapter)
    "memory": _sqlite_url(os.getenv("MEMORY_DB_PATH", str(_DATA / "memory.sqlite"))),

    # app/llm/cost_tracker.py
    # NOTE: cost_tracker.py reads MEMORY_DB_PATH but defaults to costs.db — this
    # is a naming inconsistency in the source. We use the default path directly.
    "costs": _sqlite_url(str(_DATA / "costs.db")),

    # app/db/users.py
    "auth": _sqlite_url(os.getenv("AUTH_DB_PATH", str(_DATA / "auth.db"))),

    # app/memory/knowledge_memory.py
    "knowledge": _sqlite_url(os.getenv("KNOWLEDGE_DB", str(_DATA / "knowledge.sqlite"))),

    # app/memory/learning_loop.py, app/learning/template_engine.py
    "learning": _sqlite_url(os.getenv("LEARNING_DB", str(_DATA / "learning.sqlite"))),

    # app/memory/lesson_store.py
    "lessons": _sqlite_url(os.getenv("LESSONS_DB", str(_DATA / "lessons.sqlite"))),

    # app/intelligence/file_indexer.py (path hardcoded in container.py)
    "fileindex": _sqlite_url(str(_DATA / "file_index.db")),
}

_SELECTED: str = os.getenv("AIDEVOS_MIGRATE_DB", "memory")

if _SELECTED not in _DB_URLS:
    raise ValueError(
        f"Unknown AIDEVOS_MIGRATE_DB={_SELECTED!r}. "
        f"Valid values: {sorted(_DB_URLS)}"
    )

# Each database gets a distinct alembic_version table so revision histories
# stay independent across databases.
_VERSION_TABLE = f"alembic_version_{_SELECTED}"
_TARGET_URL = _DB_URLS[_SELECTED]

# No SQLAlchemy models — all schemas are hand-authored SQL in migration files.
_TARGET_METADATA = None


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations without a live database connection (SQL script output)."""
    context.configure(
        url=_TARGET_URL,
        target_metadata=_TARGET_METADATA,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table=_VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    engine = create_engine(_TARGET_URL, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=_TARGET_METADATA,
            version_table=_VERSION_TABLE,
        )
        with context.begin_transaction():
            context.run_migrations()


# ---------------------------------------------------------------------------
# Entry point (called by Alembic CLI)
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
