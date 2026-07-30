from __future__ import annotations

from uuid import UUID

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

    Design note: instance attributes are prefixed to avoid shadowing same-named
    public methods (Python instance attrs take precedence over class methods in
    attribute lookup, so a field named ``store`` would make the ``store()``
    method unreachable via normal attribute access).
    """

    def __init__(self, repository: MemoryRepository | None = None, store: MemoryStore | None = None) -> None:
        self.repository = repository or MemoryRepository(storage=None)
        self.memory_store = store or MemoryStore()        # was: self.store   (shadowed method)
        self.memory_index = MemoryIndex()                  # was: self.index   (shadowed method)
        self.cache = MemoryCache()
        self.memory_cleanup = MemoryCleanup()              # was: self.cleanup (shadowed method)
        self.sync = MemorySynchronization()
        self._stats = MemoryStatistics()                   # was: self.statistics (shadowed method)

    def initialize(self) -> None:
        self.repository.initialize()
        self.memory_store.records.clear()
        self.cache.clear()
        self.memory_cleanup.clear()
        self.sync.mark_synced()
        self._stats = MemoryStatistics(count=self.repository.count())

    def store(self, record: MemoryRecord) -> MemoryRecord:
        """Persist a MemoryRecord through repository + all subsystems."""
        saved = self.repository.save(record)
        self.memory_store.put(str(saved.memory_id), saved)
        self.memory_index.add(str(saved.memory_id), saved)
        self.cache.set(str(saved.memory_id), saved)
        self._stats.count = self.repository.count()
        self._stats.indexed = len(self.memory_index.snapshot())
        self._stats.cached = len(self.cache._cache)
        return saved

    def retrieve(self, memory_id: UUID) -> MemoryRecord | None:
        cached = self.cache.get(str(memory_id))
        if cached is not None:
            return cached
        return self.repository.load(memory_id)

    def update(self, record: MemoryRecord) -> MemoryRecord:
        updated = self.repository.update(record)
        self.memory_store.put(str(updated.memory_id), updated)
        self.memory_index.add(str(updated.memory_id), updated)
        self.cache.set(str(updated.memory_id), updated)
        self.sync.mark_synced()
        return updated

    def delete(self, memory_id: UUID) -> bool:
        deleted = self.repository.delete(memory_id)
        self.memory_store.delete(str(memory_id))
        self.memory_index.remove(str(memory_id))
        self.cache.invalidate(str(memory_id))
        self.memory_cleanup.mark_removed(str(memory_id))
        self._stats.count = self.repository.count()
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

    def rebuild_index(self) -> None:
        """Rebuild the in-memory index from the current memory_index snapshot."""
        self._stats.indexed = len(self.memory_index.snapshot())

    def persist(self) -> None:
        self.sync.mark_synced()

    def run_cleanup(self) -> None:
        """Run the memory cleanup pass (removes tombstoned records from the cache)."""
        self.memory_cleanup.clear()

    def get_statistics(self) -> MemoryStatistics:
        """Return current memory subsystem statistics."""
        return self._stats

    def shutdown(self) -> None:
        self.memory_store.records.clear()
        self.cache.clear()
        self.memory_index = MemoryIndex()
        self.sync = MemorySynchronization()
