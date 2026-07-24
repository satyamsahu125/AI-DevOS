from __future__ import annotations

import logging
from datetime import datetime
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from ..shared.enums.memory_type import MemoryType
from ..shared.exceptions.memory import MemoryException
from ..storage.storage_adapter import StorageAdapter, StorageQuery
from .repository_filters import RepositoryFilter
from .repository_models import MemoryPage, MemoryRecord, MemorySearchResult
from .repository_query import RepositoryQuery

logger = logging.getLogger(__name__)


class RepositoryValidationException(MemoryException):
    """Raised when a repository record fails validation."""


class MemoryNotFoundException(MemoryException):
    """Raised when a repository record could not be found."""


class MemoryAlreadyExistsException(MemoryException):
    """Raised when a repository record already exists."""


class RepositoryStorageException(MemoryException):
    """Raised when the storage backend fails."""


class RepositoryQueryException(MemoryException):
    """Raised when a query is invalid."""


class RepositoryUpdateException(MemoryException):
    """Raised when an update fails."""


class RepositoryDeleteException(MemoryException):
    """Raised when a delete fails."""


class MemoryRepository:
    """Repository contract for persisting and retrieving memory records."""

    def __init__(self, storage: StorageAdapter | None = None, logger: Any | None = None) -> None:
        """Wire the optional StorageAdapter this repository persists through (None keeps records in-process only)."""
        self.storage = storage
        self.logger = logger
        self._lock = RLock()
        self._records: dict[UUID, MemoryRecord] = {}

    def initialize(self) -> None:
        """Clear the local cache and initialize the backing storage, if any."""
        self._records.clear()
        if self.storage is not None:
            self.storage.initialize()
        logger.debug("memory repository initialized: storage=%s", type(self.storage).__name__ if self.storage else None)

    def save(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a new record; raises MemoryAlreadyExistsException if its memory_id is already saved."""
        with self._lock:
            self._validate(record)
            if record.memory_id in self._records:
                raise MemoryAlreadyExistsException(f"memory {record.memory_id} already exists")
            self._assign_version(record)
            self._records[record.memory_id] = record
            if self.storage is not None:
                try:
                    self._ensure_storage_connected()
                    self.storage.insert("memory_records", self._record_to_row(record))
                except Exception as exc:
                    raise RepositoryStorageException(str(exc)) from exc
            logger.debug("memory record saved: memory_id=%s", record.memory_id)
            return record

    def load(self, memory_id: UUID) -> MemoryRecord:
        """Load a record by id, preferring storage (durable across restarts) over the local cache."""
        if self.storage is not None:
            try:
                self._ensure_storage_connected()
                rows = self.storage.select(StorageQuery(table="memory_records", filters={"memory_id": memory_id}))
                if rows:
                    return self._row_to_record(rows[0])
            except Exception as exc:
                raise RepositoryStorageException(str(exc)) from exc
        with self._lock:
            record = self._records.get(memory_id)
            if record is None:
                raise MemoryNotFoundException(f"memory {memory_id} not found")
            return record

    def update(self, record: MemoryRecord) -> MemoryRecord:
        """Update record, using storage as the source of truth when this instance's local cache is cold."""
        with self._lock:
            self._validate(record)
            existing = self._records.get(record.memory_id)
            if existing is None and self.storage is not None:
                try:
                    existing = self.load(record.memory_id)
                except MemoryNotFoundException:
                    existing = None
            if existing is None:
                raise MemoryNotFoundException(f"memory {record.memory_id} not found")
            record.version = existing.version + 1
            record.updated_at = existing.updated_at
            self._records[record.memory_id] = record
            if self.storage is not None:
                try:
                    self._ensure_storage_connected()
                    self.storage.update("memory_records", {"memory_id": record.memory_id}, self._record_to_row(record))
                except Exception as exc:
                    raise RepositoryStorageException(str(exc)) from exc
            return record

    def delete(self, memory_id: UUID) -> bool:
        with self._lock:
            if self.storage is not None:
                try:
                    self._ensure_storage_connected()
                    result = self.storage.delete("memory_records", {"memory_id": memory_id})
                    if result.deleted == 0:
                        raise MemoryNotFoundException(f"memory {memory_id} not found")
                except MemoryNotFoundException:
                    raise
                except Exception as exc:
                    raise RepositoryStorageException(str(exc)) from exc
                self._records.pop(memory_id, None)
                return True
            if memory_id not in self._records:
                raise MemoryNotFoundException(f"memory {memory_id} not found")
            del self._records[memory_id]
            return True

    def exists(self, memory_id: UUID) -> bool:
        if self.storage is not None:
            try:
                self._ensure_storage_connected()
                return self.storage.exists("memory_records", {"memory_id": memory_id})
            except Exception as exc:
                raise RepositoryStorageException(str(exc)) from exc
        with self._lock:
            return memory_id in self._records

    def find(self, query: RepositoryQuery) -> list[MemoryRecord]:
        if query.limit < 0 or query.offset < 0:
            raise RepositoryQueryException("limit and offset must be non-negative")
        if self.storage is not None:
            try:
                self._ensure_storage_connected()
                rows = self.storage.select(
                    StorageQuery(
                        table="memory_records",
                        filters=self._query_to_filters(query),
                        limit=query.limit,
                        offset=query.offset,
                        order_by=query.order_by,
                    )
                )
                return [self._row_to_record(row) for row in rows]
            except Exception as exc:
                raise RepositoryStorageException(str(exc)) from exc
        with self._lock:
            return self._apply_filters(query)

    def find_by_project(self, project_id: UUID) -> list[MemoryRecord]:
        return self.find(RepositoryQuery(project_id=project_id))

    def find_by_stage(self, stage: str) -> list[MemoryRecord]:
        return self.find(RepositoryQuery(stage=stage))

    def find_by_type(self, memory_type: MemoryType) -> list[MemoryRecord]:
        return self.find(RepositoryQuery(memory_type=memory_type))

    def list(self) -> list[MemoryRecord]:
        if self.storage is not None:
            try:
                self._ensure_storage_connected()
                rows = self.storage.select(StorageQuery(table="memory_records", filters={}, limit=0, offset=0))
                return [self._row_to_record(row) for row in rows]
            except Exception as exc:
                raise RepositoryStorageException(str(exc)) from exc
        with self._lock:
            return list(self._records.values())

    def count(self) -> int:
        if self.storage is not None:
            try:
                self._ensure_storage_connected()
                return self.storage.count("memory_records", {})
            except Exception as exc:
                raise RepositoryStorageException(str(exc)) from exc
        with self._lock:
            return len(self._records)

    def shutdown(self) -> None:
        with self._lock:
            self._records.clear()
            if self.storage is not None:
                try:
                    self.storage.shutdown()
                except Exception as exc:
                    raise RepositoryStorageException(str(exc)) from exc

    def _validate(self, record: MemoryRecord) -> None:
        if not record.content.strip():
            raise RepositoryValidationException("content is required")
        if record.memory_id is None:
            raise RepositoryValidationException("memory id is required")
        if record.project_id is None:
            raise RepositoryValidationException("project id is required")
        if record.workflow_id is None:
            raise RepositoryValidationException("workflow id is required")
        if record.version < 1:
            raise RepositoryValidationException("version must be at least 1")
        if not isinstance(record.memory_type, MemoryType):
            raise RepositoryValidationException("memory type is invalid")

    def _build_query(self, query: RepositoryQuery) -> RepositoryFilter:
        return RepositoryFilter(
            project_id=query.project_id,
            workflow_id=query.workflow_id,
            stage=query.stage,
            memory_type=query.memory_type,
            tags=query.tags,
            metadata=query.metadata,
        )

    def _apply_filters(self, query: RepositoryQuery) -> list[MemoryRecord]:
        filter_value = self._build_query(query)
        matched = []
        for record in self._records.values():
            if filter_value.project_id is not None and record.project_id != filter_value.project_id:
                continue
            if filter_value.workflow_id is not None and record.workflow_id != filter_value.workflow_id:
                continue
            if filter_value.stage is not None and record.stage != filter_value.stage:
                continue
            if filter_value.memory_type is not None and record.memory_type != filter_value.memory_type:
                continue
            if filter_value.tags and not set(filter_value.tags).issubset(set(record.tags)):
                continue
            if filter_value.metadata and not all(record.metadata.get(key) == value for key, value in filter_value.metadata.items()):
                continue
            matched.append(record)
        return matched[query.offset:query.offset + query.limit]

    def _assign_version(self, record: MemoryRecord) -> None:
        record.version = max(1, record.version)
        record.updated_at = record.created_at

    def _query_to_filters(self, query: RepositoryQuery) -> dict[str, Any]:
        filters: dict[str, Any] = {}
        if query.project_id is not None:
            filters["project_id"] = query.project_id
        if query.workflow_id is not None:
            filters["workflow_id"] = query.workflow_id
        if query.stage is not None:
            filters["stage"] = query.stage
        if query.memory_type is not None:
            filters["memory_type"] = query.memory_type
        if query.tags:
            filters["tags"] = query.tags
        if query.metadata:
            filters["metadata"] = query.metadata
        return filters

    def _ensure_storage_connected(self) -> None:
        if self.storage is None:
            return
        if not self.storage.connection.connected:
            self.storage.connect()

    def _record_to_row(self, record: MemoryRecord) -> dict[str, Any]:
        return {
            "memory_id": record.memory_id,
            "project_id": record.project_id,
            "workflow_id": record.workflow_id,
            "stage": record.stage,
            "memory_type": record.memory_type,
            "title": record.title,
            "content": record.content,
            "summary": record.summary,
            "priority": record.priority,
            "tags": list(record.tags),
            "version": record.version,
            "metadata": dict(record.metadata),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }

    def _parse_datetime(self, value: Any) -> Any:
        """Parse an ISO-format datetime string (as produced by a JSON-backed storage adapter) back to datetime."""
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return value

    def _row_to_record(self, row: dict[str, Any]) -> MemoryRecord:
        values = dict(row)
        memory_id = values.get("memory_id") or values.get("id") or uuid4()
        if isinstance(memory_id, str):
            try:
                memory_id = UUID(memory_id)
            except ValueError:
                pass
        project_id = values.get("project_id")
        if isinstance(project_id, str):
            try:
                project_id = UUID(project_id)
            except ValueError:
                pass
        workflow_id = values.get("workflow_id")
        if isinstance(workflow_id, str):
            try:
                workflow_id = UUID(workflow_id)
            except ValueError:
                pass
        memory_type = values.get("memory_type", MemoryType.Runtime)
        if not isinstance(memory_type, MemoryType):
            try:
                memory_type = MemoryType(memory_type)
            except ValueError:
                memory_type = MemoryType.Runtime
        record = MemoryRecord(
            memory_id=memory_id,
            project_id=project_id,
            workflow_id=workflow_id,
            stage=values.get("stage"),
            memory_type=memory_type,
            title=values.get("title", ""),
            content=values.get("content", ""),
            summary=values.get("summary", ""),
            priority=values.get("priority", 0),
            tags=list(values.get("tags", [])),
            version=values.get("version", 1),
            metadata=dict(values.get("metadata", {})),
            created_at=self._parse_datetime(values.get("created_at", None)) or None,
            updated_at=self._parse_datetime(values.get("updated_at", None)) or None,
        )
        return record

    def _generate_id(self) -> UUID:
        return UUID(int=0)
