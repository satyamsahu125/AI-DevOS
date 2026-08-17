from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    psycopg2 = None
    pool = None
    RealDictCursor = None
    PSYCOPG2_AVAILABLE = False

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


class PostgresStorageAdapter(StorageAdapter):
    """StorageAdapter backed by a real PostgreSQL database.

    Each logical `table` becomes a PostgreSQL table with an `id` primary key
    and a `data` column holding the row JSON-encoded. Filtering happens in
    Python (as SQLiteStorageAdapter does) so callers can pass arbitrary
    filter keys without a query-translation layer — Postgres here provides
    real persistence across process restarts, not a query engine.
    """

    def __init__(self, config: StorageConfig, logger: Any | None = None) -> None:
        """Wire the psycopg2 connection pool from config.database_url."""
        if not PSYCOPG2_AVAILABLE:
            raise RuntimeError("psycopg2 is not installed. Install psycopg2-binary to use PostgresStorageAdapter.")
        super().__init__(config=config, logger=logger)
        self._db_url = config.database_url
        if not self._db_url:
            raise ValueError("PostgresStorageAdapter requires database_url in config")
        self._connection_pool: pool.SimpleConnectionPool | None = None
        self._pool_size = config.pool_size or 1

    def initialize(self) -> None:
        """Open the connection pool so table schemas can be created on first use."""
        self._create_pool()
        self.connection.connected = False
        logger.debug("postgres storage initialized: db=%s", self._db_url)

    def _create_pool(self) -> None:
        if self._connection_pool is None:
            self._connection_pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=self._pool_size,
                dsn=self._db_url,
                cursor_factory=RealDictCursor,
            )
            self.connection.driver = "postgres"

    def connect(self) -> bool:
        """Ensure the connection pool is ready and mark this adapter connected."""
        self._validate_connection()
        if self._connection_pool is None:
            self._create_pool()
        # Test connection
        conn = self._connection_pool.getconn()
        try:
            conn.close()
        finally:
            self._connection_pool.putconn(conn)
        self.connection.connected = True
        logger.debug("postgres storage connected: db=%s", self._db_url)
        return True

    def disconnect(self) -> bool:
        """Close the connection pool."""
        if self._connection_pool is not None:
            self._connection_pool.closeall()
            self._connection_pool = None
            self.connection.connected = False
        return True

    def _get_connection(self):
        """Get a connection from the pool."""
        if self._connection_pool is None:
            self._create_pool()
        return self._connection_pool.getconn()

    def _return_connection(self, conn) -> None:
        """Return a connection to the pool."""
        if self._connection_pool is not None:
            self._connection_pool.putconn(conn)

    def _table_name(self, table: str) -> str:
        if not _TABLE_NAME_PATTERN.match(table):
            raise StorageQueryException(f"invalid table name: {table}")
        return table

    def _ensure_table(self, table: str) -> str:
        """Create the table's schema on first use for this table name."""
        name = self._table_name(table)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(f'CREATE TABLE IF NOT EXISTS "{name}" (id TEXT PRIMARY KEY, data JSONB NOT NULL)')
                conn.commit()
        finally:
            self._return_connection(conn)
        return name

    def insert(self, table: str, values: dict[str, Any]) -> StorageResult:
        """Insert a new row, keyed by memory_id/id (or a generated UUID)."""
        self._validate_connection()
        name = self._ensure_table(table)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                row = dict(values)
                key = str(row.get("memory_id") or row.get("id") or uuid4())
                cur.execute(f'SELECT id FROM "{name}" WHERE id = %s', (key,))
                if cur.fetchone() is not None:
                    raise StorageQueryException(f"record with key {key} already exists")
                row["id"] = key
                row["memory_id"] = str(row.get("memory_id", key))
                cur.execute(f'INSERT INTO "{name}" (id, data) VALUES (%s, %s)', (key, json.dumps(row, default=_json_default)))
                conn.commit()
        finally:
            self._return_connection(conn)
        return StorageResult(inserted_id=key)

    def select(self, query: StorageQuery) -> StorageResult:
        """Select rows matching the given filters."""
        self._validate_connection()
        name = self._table_name(query.table)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                filters = query.filters
                if filters:
                    where_clauses = []
                    params = []
                    for key, value in filters.items():
                        where_clauses.append(f'data->>%s = %s')
                        params.extend([key, str(value)])
                    where_sql = " AND ".join(where_clauses)
                    sql = f'SELECT id, data FROM "{name}" WHERE {where_sql}'
                else:
                    sql = f'SELECT id, data FROM "{name}"'
                    params = []

                if query.order_by:
                    order_cols = ", ".join(query.order_by)
                    sql += f" ORDER BY {order_cols}"

                sql += " LIMIT %s OFFSET %s"
                params.extend([query.limit, query.offset])

                cur.execute(sql, params)
                rows = cur.fetchall()
        finally:
            self._return_connection(conn)

        result_rows = []
        for row in rows:
            try:
                data = row["data"] if isinstance(row["data"], dict) else json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                data = {"id": row["id"]}
            data["id"] = row["id"]
            result_rows.append(data)

        return StorageResult(rows=result_rows, count=len(result_rows))

    def update(self, table: str, query: StorageQuery) -> StorageResult:
        """Update rows matching the query filters with the given values."""
        self._validate_connection()
        name = self._table_name(query.table)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                filters = query.filters
                values = query.values
                if not filters:
                    raise StorageQueryException("update requires at least one filter")
                if not values:
                    raise StorageQueryException("update requires values to set")

                where_clauses = []
                params = []
                for key, value in filters.items():
                    where_clauses.append(f'data->>%s = %s')
                    params.extend([key, str(value)])

                set_clauses = []
                for key, value in values.items():
                    set_clauses.append(f"data = jsonb_set(data, '{{{key}}}', %s)")
                    params.append(json.dumps(value, default=_json_default))

                where_sql = " AND ".join(where_clauses)
                set_sql = ", ".join(set_clauses)
                sql = f'UPDATE "{name}" SET {set_sql} WHERE {where_sql}'
                cur.execute(sql, params)
                conn.commit()
                updated = cur.rowcount
        finally:
            self._return_connection(conn)

        return StorageResult(updated=updated)

    def delete(self, table: str, query: StorageQuery) -> StorageResult:
        """Delete rows matching the query filters."""
        self._validate_connection()
        name = self._table_name(query.table)
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                filters = query.filters
                if not filters:
                    raise StorageQueryException("delete requires at least one filter")

                where_clauses = []
                params = []
                for key, value in filters.items():
                    where_clauses.append(f'data->>%s = %s')
                    params.extend([key, str(value)])

                where_sql = " AND ".join(where_clauses)
                sql = f'DELETE FROM "{name}" WHERE {where_sql}'
                cur.execute(sql, params)
                conn.commit()
                deleted = cur.rowcount
        finally:
            self._return_connection(conn)

        return StorageResult(deleted=deleted)

    def health_check(self) -> StorageHealthResult:
        """Check if the storage is healthy."""
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            self._return_connection(conn)
            return StorageHealthResult(healthy=True, message="PostgreSQL connection healthy")
        except Exception as exc:
            return StorageHealthResult(healthy=False, message=f"PostgreSQL health check failed: {exc}")

    def shutdown(self) -> None:
        """Close the connection pool."""
        if self._connection_pool is not None:
            self._connection_pool.closeall()
            self._connection_pool = None
            self.connection.connected = False