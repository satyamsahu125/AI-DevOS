from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..shared.exceptions.base import ApplicationException
from .storage_connection import StorageConnection
from .storage_transaction import StorageTransaction


@dataclass(slots=True)
class StorageConfig:
    driver: str = "memory"
    database_url: str | None = None
    pool_size: int = 1
    timeout: int = 30
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StorageQuery:
    table: str
    filters: dict[str, Any] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    limit: int = 50
    offset: int = 0
    order_by: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)


@dataclass(slots=True)
class StorageResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0
    inserted_id: Any | None = None
    updated: int = 0
    deleted: int = 0


@dataclass(slots=True)
class StorageTransactionResult:
    success: bool = False
    transaction: StorageTransaction | None = None
    error: str | None = None


@dataclass(slots=True)
class StorageHealthResult:
    healthy: bool = False
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class StorageException(ApplicationException):
    """Base exception for storage adapter failures."""


class StorageConnectionException(StorageException):
    """Raised when connection operations fail."""


class StorageQueryException(StorageException):
    """Raised when a query is invalid or cannot be executed."""


class StorageTransactionException(StorageException):
    """Raised when a transaction operation fails."""


class StorageTimeoutException(StorageException):
    """Raised when a storage operation times out."""


class StorageInitializationException(StorageException):
    """Raised when storage initialization fails."""


class StorageShutdownException(StorageException):
    """Raised when storage shutdown fails."""


class StorageAdapter(ABC):
    def __init__(self, config: StorageConfig, logger: Any | None = None) -> None:
        self.config = config
        self.logger = logger
        self.connection = StorageConnection()
        self.transaction = StorageTransaction()

    def initialize(self) -> None:
        self._open_connection()
        self.connection.connected = False

    def connect(self) -> bool:
        self._validate_connection()
        self.connection.connected = True
        return True

    def disconnect(self) -> bool:
        if self.transaction.active:
            self.rollback()
        self._close_connection()
        self.connection.connected = False
        return True

    @abstractmethod
    def insert(self, table: str, values: dict[str, Any]) -> StorageResult:
        raise NotImplementedError

    @abstractmethod
    def update(self, table: str, filters: dict[str, Any], values: dict[str, Any]) -> StorageResult:
        raise NotImplementedError

    @abstractmethod
    def delete(self, table: str, filters: dict[str, Any]) -> StorageResult:
        raise NotImplementedError

    @abstractmethod
    def select(self, query: StorageQuery) -> list[dict[str, Any]]:
        raise NotImplementedError

    def exists(self, table: str, filters: dict[str, Any]) -> bool:
        return self.count(table, filters) > 0

    def count(self, table: str, filters: dict[str, Any]) -> int:
        result = self.select(StorageQuery(table=table, filters=filters, limit=0, offset=0))
        return len(result)

    def search(self, query: StorageQuery) -> list[dict[str, Any]]:
        return self.select(query)

    def begin_transaction(self) -> StorageTransactionResult:
        if self.transaction.active:
            raise StorageTransactionException("a transaction is already active")
        self.transaction.active = True
        self.transaction.committed = False
        return StorageTransactionResult(success=True, transaction=self.transaction)

    def commit(self) -> StorageTransactionResult:
        if not self.transaction.active:
            raise StorageTransactionException("no active transaction to commit")
        self.transaction.committed = True
        self.transaction.active = False
        return StorageTransactionResult(success=True, transaction=self.transaction)

    def rollback(self) -> StorageTransactionResult:
        if not self.transaction.active:
            raise StorageTransactionException("no active transaction to rollback")
        self.transaction.active = False
        self.transaction.committed = False
        return StorageTransactionResult(success=True, transaction=self.transaction)

    @abstractmethod
    def health(self) -> StorageHealthResult:
        raise NotImplementedError

    def shutdown(self) -> None:
        self.disconnect()

    @abstractmethod
    def _open_connection(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def _close_connection(self) -> None:
        raise NotImplementedError

    def _validate_connection(self) -> None:
        if self.config is None:
            raise StorageConnectionException("storage config is missing")

    @abstractmethod
    def _map_result(self, result: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def _execute(self, query: StorageQuery) -> list[dict[str, Any]]:
        raise NotImplementedError


class MemoryStorageAdapter(StorageAdapter):
    def __init__(self, config: StorageConfig, logger: Any | None = None) -> None:
        super().__init__(config=config, logger=logger)
        self._store: dict[str, dict[str, dict[str, Any]]] = {}

    def initialize(self) -> None:
        self._store.clear()
        self.connection = StorageConnection(connected=False, driver=self.config.driver)
        self.transaction = StorageTransaction(active=False, committed=False)

    def _open_connection(self) -> None:
        self.connection.driver = self.config.driver

    def _close_connection(self) -> None:
        self.connection.connected = False

    def insert(self, table: str, values: dict[str, Any]) -> StorageResult:
        self._validate_connection()
        table_store = self._store.setdefault(table, {})
        row = dict(values)
        key = str(row.get("memory_id") or row.get("id") or uuid4())
        if key in table_store:
            raise StorageQueryException(f"record with key {key} already exists")
        row["id"] = key
        row["memory_id"] = str(row.get("memory_id", key))
        table_store[key] = row
        return StorageResult(rows=[self._copy_row(row)], count=1, inserted_id=key)

    def update(self, table: str, filters: dict[str, Any], values: dict[str, Any]) -> StorageResult:
        self._validate_connection()
        table_store = self._store.get(table, {})
        updated_rows: list[dict[str, Any]] = []
        for key, row in table_store.items():
            if self._match_filters(row, filters):
                updated = dict(row)
                updated.update(values)
                updated["memory_id"] = str(updated.get("memory_id", key))
                table_store[key] = updated
                updated_rows.append(self._copy_row(updated))
        return StorageResult(rows=updated_rows, count=len(updated_rows), updated=len(updated_rows))

    def delete(self, table: str, filters: dict[str, Any]) -> StorageResult:
        self._validate_connection()
        table_store = self._store.get(table, {})
        removed = []
        for key in list(table_store.keys()):
            if self._match_filters(table_store[key], filters):
                removed.append(table_store.pop(key))
        return StorageResult(rows=[self._copy_row(row) for row in removed], count=len(removed), deleted=len(removed))

    def select(self, query: StorageQuery) -> list[dict[str, Any]]:
        self._validate_connection()
        rows = self._execute(query)
        return self._map_result(rows)

    def health(self) -> StorageHealthResult:
        return StorageHealthResult(
            healthy=self.connection.connected,
            message="connected" if self.connection.connected else "disconnected",
            metadata={"driver": self.connection.driver},
        )

    def shutdown(self) -> None:
        self._store.clear()
        self.connection.connected = False
        self.transaction = StorageTransaction(active=False, committed=False)

    def _open_connection(self) -> None:
        self.connection.connected = True

    def _close_connection(self) -> None:
        self.connection.connected = False

    def _copy_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return dict(row)

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
                if actual != expected:
                    return False
        return True

    def _map_result(self, result: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._copy_row(row) for row in result]

    def _execute(self, query: StorageQuery) -> list[dict[str, Any]]:
        table_store = self._store.get(query.table, {})
        if not table_store:
            return []
        rows = [row for row in table_store.values() if self._match_filters(row, query.filters)]
        if query.order_by:
            for key in reversed(query.order_by):
                rows.sort(key=lambda row: row.get(key))
        if query.limit > 0:
            rows = rows[query.offset : query.offset + query.limit]
        else:
            rows = rows[query.offset :]
        return rows
