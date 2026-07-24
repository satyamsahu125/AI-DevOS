from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID, uuid5

from ..shared.enums.memory_type import MemoryType
from ..storage.storage_adapter import StorageConfig
from ..storage.storage_factory import StorageFactory
from .memory_repository import MemoryRecord, MemoryRepository

logger = logging.getLogger(__name__)

_FLAT_KEY_NAMESPACE = UUID(int=0)


class MemoryManager:
    """Simple key/value memory store used by ContextManager and ProjectInitializer.

    Backed by MemoryRepository against a real SQLite database at
    `root/memory.db` (created on first use). Any `.txt` files left over
    from the previous flat-file implementation are imported into SQLite
    the first time that database is created.
    """

    def __init__(self, root: Path | None = None, repository: MemoryRepository | None = None) -> None:
        """Wire the on-disk root and the MemoryRepository/SQLite backend used to persist entries."""
        self.root = root or Path(__file__).resolve().parents[1] / "memory"
        self.root.mkdir(parents=True, exist_ok=True)

        if repository is not None:
            self.repository = repository
            return

        db_path = self.root / "memory.db"
        needs_migration = not db_path.exists()
        config = StorageConfig(driver="sqlite", database_url=str(db_path))
        adapter = StorageFactory.create(config)
        adapter.connect()
        self.repository = MemoryRepository(storage=adapter)
        self.repository.initialize()
        logger.debug("memory manager backed by sqlite: db=%s", db_path)

        if needs_migration:
            self._migrate_txt_files()

    def initialize(self, project_name: str) -> Path:
        """Create (if needed) and return the workspace-memory directory for project_name."""
        project_root = self.root / project_name.replace(" ", "-").lower()
        project_root.mkdir(parents=True, exist_ok=True)
        logger.debug("memory initialized: project_name=%s", project_name)
        return project_root

    def _key(self, project_id: str, key: str) -> str:
        """Namespace key by project_id so no two projects can ever collide on the same key."""
        return f"{project_id}:{key}"

    def store(self, project_id: str, key: str, value: str) -> None:
        """Persist value under key within project_id's namespace, creating or updating the record."""
        namespaced = self._key(project_id, key)
        logger.debug("store: key=%s", namespaced)
        existing = self._find_record(namespaced)
        if existing is not None:
            existing.content = value
            self.repository.update(existing)
            return
        record = MemoryRecord(
            memory_id=self._key_to_id(namespaced),
            project_id=_FLAT_KEY_NAMESPACE,
            workflow_id=_FLAT_KEY_NAMESPACE,
            memory_type=MemoryType.Runtime,
            title=namespaced,
            content=value,
        )
        self.repository.save(record)

    def load(self, project_id: str, key: str) -> str | None:
        """Return the value stored under key within project_id's namespace, or None if never stored."""
        namespaced = self._key(project_id, key)
        logger.debug("load: key=%s", namespaced)
        record = self._find_record(namespaced)
        return record.content if record is not None else None

    def list_for_project(self, project_id: str) -> list[MemoryRecord]:
        """Return every record namespaced under project_id (title starting with "{project_id}:")."""
        prefix = f"{project_id}:"
        return [record for record in self.repository.list() if record.title.startswith(prefix)]

    def delete_project(self, project_id: str) -> int:
        """Delete every record namespaced under project_id. Returns how many were deleted."""
        records = self.list_for_project(project_id)
        for record in records:
            self.repository.delete(record.memory_id)
        return len(records)

    def _find_record(self, key: str) -> MemoryRecord | None:
        memory_id = self._key_to_id(key)
        if self.repository.exists(memory_id):
            return self.repository.load(memory_id)
        return None

    def _key_to_id(self, key: str) -> UUID:
        return uuid5(_FLAT_KEY_NAMESPACE, key)

    def _migrate_txt_files(self) -> None:
        """Import any pre-existing `<key>.txt` files in root into the new SQLite backend.

        These predate per-project namespacing entirely, so they are saved
        under their raw (un-namespaced) key rather than going through
        store(), which now requires a project_id.
        """
        migrated = 0
        for txt_file in self.root.glob("*.txt"):
            key = txt_file.stem
            if self._find_record(key) is None:
                record = MemoryRecord(
                    memory_id=self._key_to_id(key),
                    project_id=_FLAT_KEY_NAMESPACE,
                    workflow_id=_FLAT_KEY_NAMESPACE,
                    memory_type=MemoryType.Runtime,
                    title=key,
                    content=txt_file.read_text(encoding="utf-8"),
                )
                self.repository.save(record)
                migrated += 1
        if migrated:
            logger.info("migrated %s legacy .txt memory files into sqlite", migrated)
