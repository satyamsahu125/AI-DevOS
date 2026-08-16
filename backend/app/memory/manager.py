import logging
import os
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
        # Phase 6 MIGRATE: anchored default — parents[2] from backend/app/memory/ = backend/.
        # Env var MEMORY_DB overrides; explicit root= (tests / DI) takes precedence over both.
        _data_dir = Path(__file__).resolve().parents[2] / "data"
        _data_dir.mkdir(parents=True, exist_ok=True)
        _default_db = Path(os.getenv("MEMORY_DB", str(_data_dir / "memory.sqlite")))
        if root is not None:
            db_path = root / "memory.sqlite"
            self.root = root
        else:
            db_path = _default_db
            self.root = db_path.parent
        self.root.mkdir(parents=True, exist_ok=True)

        if repository is not None:
            self.repository = repository
            return

        db_path.parent.mkdir(parents=True, exist_ok=True)
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

    def store_stage_output(self, project_id: str, stage_name: str, content: str) -> None:
        """Persist an approved stage output under a per-stage namespace key.

        Replaces the single-slot workflow:latest_message pattern. Each stage's
        output is stored independently so any downstream stage can read any
        predecessor without it being overwritten by the next stage.
        """
        self.store(project_id, f"workflow:stage:{stage_name}", content)
        logger.debug("store_stage_output: project=%s stage=%s bytes=%d", project_id, stage_name, len(content))

    def load_stage_output(self, project_id: str, stage_name: str) -> str | None:
        """Return the approved output for stage_name, or None if not yet run."""
        return self.load(project_id, f"workflow:stage:{stage_name}")

    def store_sprint_stage_output(
        self, project_id: str, sprint_number: int, stage_name: str, content: str
    ) -> None:
        """Persist a sprint-scoped stage output.

        Uses key ``sprint:{sprint_number}:stage:{stage_name}`` so Sprint 1 and
        Sprint 2 outputs for the same stage never collide.  Cross-sprint
        canonical outputs (Architect, ProductOwner, etc.) should continue to
        use :meth:`store_stage_output`.
        """
        key = f"sprint:{sprint_number}:stage:{stage_name}"
        self.store(project_id, key, content)
        logger.debug(
            "store_sprint_stage_output: project=%s sprint=%d stage=%s bytes=%d",
            project_id, sprint_number, stage_name, len(content),
        )

    def load_sprint_stage_output(
        self, project_id: str, sprint_number: int, stage_name: str
    ) -> str | None:
        """Return the approved output for stage_name within sprint_number, or None."""
        key = f"sprint:{sprint_number}:stage:{stage_name}"
        return self.load(project_id, key)

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

    def get_knowledge_memory(self, project_id: str):
        """Return the per-project KnowledgeMemory instance for project_id.

        Delegates to KnowledgeMemoryFactory.get_or_create() so that each
        project gets its own isolated HNSW index and SQLite database.
        The factory caches the returned instance — calling this method
        multiple times with the same project_id returns the same object.

        This method exists as a convenience on MemoryManager so callers
        that already hold a MemoryManager reference don't need to import
        KnowledgeMemoryFactory directly.

        Returns
        -------
        KnowledgeMemory
            Per-project isolated semantic knowledge store.
        """
        from .knowledge_memory import KnowledgeMemoryFactory
        return KnowledgeMemoryFactory.get_or_create(project_id)

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
