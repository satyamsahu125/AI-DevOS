"""Add workflow_events table for event sourcing.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-17

This migration adds the workflow_events table for event sourcing.
"""
from __future__ import annotations

from alembic import op

revision: str = "0002"
down_revision: str = "0001"
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # workflow_events table for event sourcing
    op.execute("""
        CREATE TABLE IF NOT EXISTS workflow_events (
            event_id    TEXT PRIMARY KEY,
            workflow_id TEXT    NOT NULL,
            trace_id    TEXT,
            stage       TEXT,
            event_type  TEXT    NOT NULL,
            actor       TEXT    NOT NULL,
            artifact_id TEXT,
            payload     TEXT,  -- JSON
            created_at  TEXT    NOT NULL
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_workflow_events_workflow_created
            ON workflow_events(workflow_id, created_at)
    """)


def downgrade() -> None:
    # Baseline — downgrade is a no-op by design.
    pass