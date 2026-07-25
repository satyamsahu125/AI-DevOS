from __future__ import annotations

from typing import Any
from uuid import UUID

from ..shared.enums.memory_type import MemoryType
from .memory_cache import MemoryCache
from .memory_cleanup import MemoryCleanup
from .memory_index import MemoryIndex
from .memory_statistics import MemoryStatistics
from .memory_store import MemoryStore
from .memory_sync import MemorySynchronization
from .memory_repository import MemoryRepository
from .repository_models import MemoryRecord
from .repository_query import RepositoryQuery


class MemoryOrchestrator:
    """MemoryOrchestrator coordinates all memory subsystems (repository, store, index, cache, cleanup, sync, statistics).

    For simple key/value storage, use MemoryManager from manager.py.
    """

    def __init__(self, repository: MemoryRepository | None = None, store: MemoryStore | None = None) -> None:
        self.repository = repository or MemoryRepository(storage=None)
        self.store = store or MemoryStore()
        self.index = MemoryIndex()
        self.cache = MemoryCache()
        self.cleanup = MemoryCleanup()
        self.sync = MemorySynchronization()
        self.statistics = MemoryStatistics()

    def initialize(self) -> None:
        self.repository.initialize()
        self.store.records.clear()
        self.cache.clear()
        self.cleanup.clear()
        self.sync.mark_synced()
        self.statistics = MemoryStatistics(count=self.repository.count())

    def store(self, record: MemoryRecord) -> MemoryRecord:
        saved = self.repository.save(record)
        self.store.put(str(saved.memory_id), saved)
        self.index.add(str(saved.memory_id), saved)
        self.cache.set(str(saved.memory_id), saved)
        self.statistics.count = self.repository.count()
        self.statistics.indexed = len(self.index.snapshot())
        self.statistics.cached = len(self.cache._cache)
        return saved

    def retrieve(self, memory_id: UUID) -> MemoryRecord | None:
        cached = self.cache.get(str(memory_id))
        if cached is not None:
            return cached
        return self.repository.load(memory_id)

    def update(self, record: MemoryRecord) -> MemoryRecord:
        updated = self.repository.update(record)
        self.store.put(str(updated.memory_id), updated)
        self.index.add(str(updated.memory_id), updated)
        self.cache.set(str(updated.memory_id), updated)
        self.sync.mark_synced()
        return updated

    def delete(self, memory_id: UUID) -> bool:
        deleted = self.repository.delete(memory_id)
        self.store.delete(str(memory_id))
        self.index.remove(str(memory_id))
        self.cache.invalidate(str(memory_id))
        self.cleanup.mark_removed(str(memory_id))
        self.statistics.count = self.repository.count()
        return deleted

    def search(self, query: RepositoryQuery) -> list[MemoryRecord]:
        results = self.repository.find(query)
        self.sync.mark_synced()
        return results

    def summarize(self, memory_id: UUID) -> str:
        record = self.retrieve(memory_id)
        if record is None:
            return ""
        return record.summary or record.content[:80]

    def index(self) -> None:
        self.statistics.indexed = len(self.index.snapshot())

    def persist(self) -> None:
        self.sync.mark_synced()

    def cleanup(self) -> None:
        self.cleanup.clear()

    def statistics(self) -> MemoryStatistics:
        return self.statistics

    def shutdown(self) -> None:
        self.store.records.clear()
        self.cache.clear()
        self.index = MemoryIndex()
        self.sync = MemorySynchronization()
