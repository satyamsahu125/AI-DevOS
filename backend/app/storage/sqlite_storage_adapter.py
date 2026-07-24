from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .storage_adapter import (
    StorageAdapter,
    StorageConfig,
    StorageHealthResult,
    StorageQuery,
    StorageQueryException,
    StorageResult,
)

logger = logging.getLogger(__name__)

_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _json_default(value: Any) -> str:
    """Serialize the value types MemoryRecord rows can contain but json can't handle natively."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class SQLiteStorageAdapter(StorageAdapter):
    """StorageAdapter backed by a real on-disk SQLite database.

    Each logical `table` becomes a SQLite table with an `id` primary key
    and a `data` column holding the row JSON-encoded. Filtering happens in
    Python (as MemoryStorageAdapter does) so callers can pass arbitrary
    filter keys without a query-translation layer -- SQLite here provides
    real persistence across process restarts, not a query engine.
    """

    def __init__(self, config: StorageConfig, logger: Any | None = None) -> None:
        """Wire the sqlite3 connection target from config.database_url (or an in-memory db)."""
        super().__init__(config=config, logger=logger)
        self._db_path = config.database_url or ":memory:"
        if self._db_path != ":memory:":
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        """Open the sqlite3 connection so table schemas can be created on first use."""
        self._open_connection()
        self.connection.connected = False
        logger.debug("sqlite storage initialized: db=%s", self._db_path)

    def connect(self) -> bool:
        """Open the sqlite3 connection if needed and mark this adapter connected."""
        self._validate_connection()
        if self._conn is None:
            self._open_connection()
        self.connection.connected = True
        logger.debug("sqlite storage connected: db=%s", self._db_path)
        return True

    def _open_connection(self) -> None:
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self.connection.driver = "sqlite"

    def _close_connection(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _table_name(self, table: str) -> str:
        if not _TABLE_NAME_PATTERN.match(table):
            raise StorageQueryException(f"invalid table name: {table}")
        return table

    def _ensure_table(self, table: str) -> str:
        """Create the table's schema on first use for this table name."""
        name = self._table_name(table)
        assert self._conn is not None
        self._conn.execute(f'CREATE TABLE IF NOT EXISTS "{name}" (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self._conn.commit()
        return name

    def insert(self, table: str, values: dict[str, Any]) -> StorageResult:
        """Insert a new row, keyed by memory_id/id (or a generated UUID)."""
        self._validate_connection()
        name = self._ensure_table(table)
        assert self._conn is not None
        row = dict(values)
        key = str(row.get("memory_id") or row.get("id") or uuid4())
        existing = self._conn.execute(f'SELECT id FROM "{name}" WHERE id = ?', (key,)).fetchone()
        if existing is not None:
            raise StorageQueryException(f"record with key {key} already exists")
        row["id"] = key
        row["memory_id"] = str(row.get("memory_id", key))
        self._conn.execute(f'INSERT INTO "{name}" (id, data) VALUES (?, ?)', (key, json.dumps(row, default=_json_default)))
        self._conn.commit()
        logger.debug("sqlite insert: table=%s id=%s", name, key)
        return StorageResult(rows=[dict(row)], count=1, inserted_id=key)

    def update(self, table: str, filters: dict[str, Any], values: dict[str, Any]) -> StorageResult:
        """Update every row matching filters, merging in values."""
        self._validate_connection()
        name = self._ensure_table(table)
        updated_rows: list[dict[str, Any]] = []
        for key, row in self._all_rows(name):
            if self._match_filters(row, filters):
                merged = dict(row)
                merged.update(values)
                merged["memory_id"] = str(merged.get("memory_id", key))
                assert self._conn is not None
                self._conn.execute(f'UPDATE "{name}" SET data = ? WHERE id = ?', (json.dumps(merged, default=_json_default), key))
                updated_rows.append(merged)
        if updated_rows:
            assert self._conn is not None
            self._conn.commit()
        logger.debug("sqlite update: table=%s matched=%s", name, len(updated_rows))
        return StorageResult(rows=updated_rows, count=len(updated_rows), updated=len(updated_rows))

    def delete(self, table: str, filters: dict[str, Any]) -> StorageResult:
        """Delete every row matching filters."""
        self._validate_connection()
        name = self._ensure_table(table)
        assert self._conn is not None
        removed: list[dict[str, Any]] = []
        for key, row in self._all_rows(name):
            if self._match_filters(row, filters):
                self._conn.execute(f'DELETE FROM "{name}" WHERE id = ?', (key,))
                removed.append(row)
        if removed:
            self._conn.commit()
        logger.debug("sqlite delete: table=%s removed=%s", name, len(removed))
        return StorageResult(rows=removed, count=len(removed), deleted=len(removed))

    def select(self, query: StorageQuery) -> list[dict[str, Any]]:
        """Select rows from the table matching query.filters, ordered/paged as requested."""
        self._validate_connection()
        rows = self._execute(query)
        return self._map_result(rows)

    def health(self) -> StorageHealthResult:
        """Report whether this adapter currently holds an open sqlite3 connection."""
        return StorageHealthResult(
            healthy=self.connection.connected,
            message="connected" if self.connection.connected else "disconnected",
            metadata={"driver": "sqlite", "database": self._db_path},
        )

    def shutdown(self) -> None:
        """Close the underlying sqlite3 connection."""
        self.disconnect()

    def _map_result(self, result: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(row) for row in result]

    def _execute(self, query: StorageQuery) -> list[dict[str, Any]]:
        name = self._ensure_table(query.table)
        rows = [row for _, row in self._all_rows(name) if self._match_filters(row, query.filters)]
        if query.order_by:
            for key in reversed(query.order_by):
                rows.sort(key=lambda row: row.get(key))
        if query.limit > 0:
            rows = rows[query.offset : query.offset + query.limit]
        else:
            rows = rows[query.offset :]
        return rows

    def _all_rows(self, table: str) -> list[tuple[str, dict[str, Any]]]:
        assert self._conn is not None
        cursor = self._conn.execute(f'SELECT id, data FROM "{table}"')
        return [(key, json.loads(data)) for key, data in cursor.fetchall()]

    def _match_filters(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            actual = row.get(key)
            if isinstance(expected, list):
                if not isinstance(actual, list) or not set(expected).issubset(set(actual)):
                    return False
            elif isinstance(expected, dict):
                if not isinstance(actual, dict):
                    return False
                for sub_key, sub_value in expected.items():
                    if actual.get(sub_key) != sub_value:
                        return False
            else:
                if actual != str(expected) and actual != expected:
                    return False
        return True
