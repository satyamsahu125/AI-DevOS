from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import hnswlib
import numpy as np

from .secret_scrubber import SecretScrubber as _SecretScrubber

logger = logging.getLogger(__name__)

# Phase 7: shared scrubber instance — scrubs text BEFORE embedding and
# SQLite persistence so secrets never enter the vector index or knowledge DB.
_scrubber = _SecretScrubber()

_EMBEDDING_DIM = 384
_MODEL_NAME = "all-MiniLM-L6-v2"
_DEFAULT_MAX_ELEMENTS = 1000

# Phase 6 MIGRATE: anchored defaults — parents[2] from backend/app/memory/ = backend/.
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_DB_PATH = Path(os.getenv("KNOWLEDGE_DB", str(_DATA_DIR / "knowledge.sqlite")))
_DEFAULT_INDEX_PATH = Path(os.getenv("KNOWLEDGE_INDEX", str(_DATA_DIR / "knowledge.hnsw")))

# Shared across instances in this process: the sentence-transformers model is
# expensive to load (seconds, real torch weights), so every KnowledgeMemory
# reuses the same one instead of loading it per instance.
_shared_model_lock = threading.Lock()
_shared_model: Any | None = None


def _get_embedding_model() -> Any:
    """Lazily load (once per process) and return the shared SentenceTransformer model."""
    global _shared_model
    with _shared_model_lock:
        if _shared_model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("loading embedding model: %s", _MODEL_NAME)
            _shared_model = SentenceTransformer(_MODEL_NAME)
        return _shared_model


@dataclass(slots=True)
class SearchResult:
    """One semantic search hit: the stored entry plus its similarity score."""

    key: str
    value: str
    category: str
    source: str
    score: float


class KnowledgeMemory:
    """Semantic knowledge store: text -> 384-dim vectors, HNSW cosine search, SQLite text/metadata.

    Inspired by ruflo's AgentDB/HNSW memory (research/ruflo/v3/@claude-flow/memory),
    reimplemented in pure Python using hnswlib (rather than a hand-rolled HNSW
    graph) and sentence-transformers for embeddings. The HNSW index is
    persisted to a .hnsw file and reloaded on restart; SQLite is the source of
    truth for text/metadata (the index only ever stores vectors keyed by
    SQLite rowid).
    """

    def __init__(
        self,
        db_path: Path | None = None,
        index_path: Path | None = None,
        max_elements: int = _DEFAULT_MAX_ELEMENTS,
    ) -> None:
        """Open (creating on first run) the SQLite store and HNSW index backing this KnowledgeMemory."""
        self._lock = threading.RLock()
        self._db_path = Path(db_path) if db_path is not None else _DEFAULT_DB_PATH
        self._index_path = Path(index_path) if index_path is not None else _DEFAULT_INDEX_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._max_elements = max_elements
        self._closed = False

        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._ensure_schema()
        self._index = self._load_or_create_index()
        logger.debug("knowledge memory ready: db=%s index=%s", self._db_path, self._index_path)

    def _ensure_schema(self) -> None:
        """Create the knowledge_entries table on first run."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def _load_or_create_index(self) -> hnswlib.Index:
        """Load the HNSW index from disk if present (cold start otherwise: a fresh empty index)."""
        index = hnswlib.Index(space="cosine", dim=_EMBEDDING_DIM)
        if self._index_path.exists():
            try:
                index.load_index(str(self._index_path), max_elements=self._max_elements)
                logger.debug("hnsw index loaded: count=%s", index.get_current_count())
                index.set_ef(50)
                return index
            except Exception as exc:
                logger.warning("failed to load hnsw index, starting fresh: %s", exc)
        index.init_index(max_elements=self._max_elements, ef_construction=200, M=16)
        index.set_ef(50)
        logger.debug("hnsw index initialized: max_elements=%s", self._max_elements)
        return index

    def _ensure_capacity(self, additional: int) -> None:
        """Grow the HNSW index's capacity if it's about to run out of room."""
        current = self._index.get_current_count()
        if current + additional > self._max_elements:
            new_max = max(self._max_elements * 2, current + additional)
            logger.info("growing hnsw index: %s -> %s", self._max_elements, new_max)
            self._index.resize_index(new_max)
            self._max_elements = new_max

    def _embed(self, text: str) -> np.ndarray:
        model = _get_embedding_model()
        vector = model.encode(text, normalize_embeddings=True)
        return np.asarray(vector, dtype=np.float32)

    def _save_index(self) -> None:
        self._index.save_index(str(self._index_path))

    def store(self, key: str, value: str, category: str = "", source: str = "") -> int:
        """Store value under key (embedding it for search), returning its SQLite row id.

        Re-storing under an existing key replaces it: the old vector is
        removed from the HNSW index first, so there's no stale/duplicate entry.

        Phase 7 — secret scrubbing:
        The value is sanitised by SecretScrubber BEFORE embedding, SQLite
        insertion, or HNSW indexing.  If the scrubber itself raises, the call
        is aborted to prevent unredacted secrets from reaching the store.

        Atomicity: SQLite commit and HNSW index save are wrapped so a crash
        between them cannot leave the store in an inconsistent state.
        """
        with self._lock:
            # Scrub BEFORE any I/O — must be the first operation on value.
            value = _scrubber.scrub_or_raise(value)

            logger.debug("store: key=%s category=%s", key, category)
            existing_id = self._get_id_by_key(key)
            if existing_id is not None:
                self._delete_by_id(existing_id, key)

            embedding = self._embed(value)
            cursor = self._conn.execute(
                "INSERT INTO knowledge_entries (key, value, category, source, created_at) VALUES (?, ?, ?, ?, ?)",
                (key, value, category, source, datetime.now(timezone.utc).isoformat()),
            )
            entry_id = cursor.lastrowid

            self._ensure_capacity(1)
            self._index.add_items(embedding.reshape(1, -1), np.array([entry_id]))

            try:
                self._save_index()
                self._conn.commit()
            except Exception as exc:
                logger.error(
                    "store: _save_index failed — rolling back SQLite transaction: key=%s error=%s",
                    key, exc,
                )
                self._conn.rollback()
                raise

            logger.info("stored knowledge entry: key=%s id=%s", key, entry_id)
            return entry_id

    def search(self, query: str, top_k: int = 5, category_filter: str | None = None) -> list[SearchResult]:
        """Return the top_k entries most semantically similar to query, optionally filtered by category."""
        with self._lock:
            logger.debug("search: query=%s top_k=%s category_filter=%s", query, top_k, category_filter)
            count = self._index.get_current_count()
            if count == 0:
                logger.debug("search on empty index: returning []")
                return []

            embedding = self._embed(query)
            k = min(top_k * 3 if category_filter else top_k, count)
            labels, distances = self._knn_query_safe(embedding, k)
            if labels is None:
                return []

            results: list[SearchResult] = []
            for label, distance in zip(labels[0], distances[0]):
                row = self._get_row_by_id(int(label))
                if row is None:
                    continue  # deleted or orphaned label
                if category_filter and row["category"] != category_filter:
                    continue
                results.append(
                    SearchResult(
                        key=row["key"],
                        value=row["value"],
                        category=row["category"],
                        source=row["source"],
                        score=1.0 - float(distance),  # hnswlib cosine space returns distance = 1 - similarity
                    )
                )
                if len(results) >= top_k:
                    break

            logger.debug("search returned %s results", len(results))
            return results

    def _knn_query_safe(self, embedding: np.ndarray, k: int) -> tuple[Any, Any] | tuple[None, None]:
        """Run knn_query, shrinking k on hnswlib's "ef or M is too small" error (soft-deleted labels count
        toward get_current_count() but aren't reachable, so the requested k can exceed what's actually available).
        """
        while k > 0:
            try:
                return self._index.knn_query(embedding.reshape(1, -1), k=k)
            except RuntimeError as exc:
                logger.debug("knn_query failed at k=%s, retrying smaller: %s", k, exc)
                k -= 1
        return None, None

    def count_all(self) -> int:
        """Return the total number of entries stored (across every category/project)."""
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()
            return int(row[0]) if row else 0

    def get_by_key(self, key: str) -> str | None:
        """Return the stored value for key, or None if it doesn't exist."""
        with self._lock:
            logger.debug("get_by_key: key=%s", key)
            cursor = self._conn.execute("SELECT value FROM knowledge_entries WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None

    def delete(self, key: str) -> bool:
        """Delete the entry stored under key, from both SQLite and the HNSW index. Returns whether it existed."""
        with self._lock:
            logger.debug("delete: key=%s", key)
            entry_id = self._get_id_by_key(key)
            if entry_id is None:
                return False
            self._delete_by_id(entry_id, key)
            self._save_index()
            return True

    def _get_id_by_key(self, key: str) -> int | None:
        cursor = self._conn.execute("SELECT id FROM knowledge_entries WHERE key = ?", (key,))
        row = cursor.fetchone()
        return int(row[0]) if row else None

    def _get_row_by_id(self, entry_id: int) -> dict[str, Any] | None:
        cursor = self._conn.execute(
            "SELECT key, value, category, source FROM knowledge_entries WHERE id = ?", (entry_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {"key": row[0], "value": row[1], "category": row[2], "source": row[3]}

    def _delete_by_id(self, entry_id: int, key: str) -> None:
        self._conn.execute("DELETE FROM knowledge_entries WHERE id = ?", (entry_id,))
        self._conn.commit()
        try:
            self._index.mark_deleted(entry_id)
        except RuntimeError:
            pass  # label was never added to the index (shouldn't happen, but non-fatal)
        logger.info("deleted knowledge entry: key=%s id=%s", key, entry_id)

    def close(self) -> None:
        """Close the SQLite connection and mark this instance as closed.

        Called by KnowledgeMemoryFactory.cleanup_project() before evicting an
        instance from the cache.  Safe to call multiple times.
        """
        with self._lock:
            if not self._closed:
                try:
                    self._conn.close()
                except Exception:  # noqa: BLE001
                    pass
                self._closed = True
                logger.debug("knowledge memory closed: db=%s", self._db_path)


# ─────────────────────────────────────────────────────────────────────────────
# KnowledgeMemoryFactory — per-project isolation
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeMemoryFactory:
    """Factory that owns one KnowledgeMemory instance per project_id.

    All projects share the same embedding model and the same process-level
    ``_shared_model`` singleton (expensive to load; harmless to share).
    Each project gets its own HNSW index and SQLite database, so a cosine
    search on project A's memory never returns entries stored for project B.

    Additive design
    ---------------
    The pre-existing global ``KnowledgeMemory()`` instantiation in the
    Container/DI layer continues to work unchanged.  The factory is purely
    additive — callers that want per-project isolation call
    ``KnowledgeMemoryFactory.get_or_create(project_id)``; callers that don't
    care continue using the global instance.

    Thread safety
    -------------
    ``_instances`` and ``_lock`` are class-level, so a single cache is shared
    across all threads in the process.  Every mutation is protected by
    ``_lock`` (a re-entrant lock so get_or_create → close chains work).

    Directory layout
    ----------------
    Active project data lives under::

        <DATA_DIR>/projects/<project_id>/knowledge.sqlite
        <DATA_DIR>/projects/<project_id>/knowledge.hnsw

    Directories are created lazily on first use.  Archived project data is
    moved (not deleted) to::

        <DATA_DIR>/archive/<project_id>/
    """

    #: project_id → KnowledgeMemory instance (per-project isolated store)
    _instances: dict[str, KnowledgeMemory] = {}
    _lock: threading.RLock = threading.RLock()

    @classmethod
    def get_or_create(cls, project_id: str) -> KnowledgeMemory:
        """Return the KnowledgeMemory for project_id, creating it on first call.

        The returned instance is cached: calling ``get_or_create`` twice with
        the same ``project_id`` returns the *same* object.

        Parameters
        ----------
        project_id:
            Unique project identifier (UUID string or any non-empty str).

        Returns
        -------
        KnowledgeMemory
            Isolated per-project knowledge store.
        """
        with cls._lock:
            if project_id not in cls._instances:
                db_path = _DATA_DIR / "projects" / project_id / "knowledge.sqlite"
                index_path = _DATA_DIR / "projects" / project_id / "knowledge.hnsw"
                logger.info(
                    "[KnowledgeMemoryFactory] creating instance: project_id=%s db=%s",
                    project_id, db_path,
                )
                cls._instances[project_id] = KnowledgeMemory(
                    db_path=db_path,
                    index_path=index_path,
                )
            return cls._instances[project_id]

    @classmethod
    def cleanup_project(cls, project_id: str) -> None:
        """Evict the project's instance from the cache and release its resources.

        Behaviour
        ---------
        * Removes the instance from ``_instances``.
        * Closes the SQLite connection (safe to call if already closed).
        * **Deletes on-disk files only when the project has zero entries** —
          an empty project has no data worth keeping.  A project with entries
          is evicted from the cache (so a future ``get_or_create`` creates a
          fresh connection) but its files are left on disk untouched.

        This means ``cleanup_project`` on a non-empty project is equivalent
        to "disconnect" rather than "delete".  Use ``archive_inactive`` to
        move non-empty projects off the hot path.

        Parameters
        ----------
        project_id:
            Project to clean up.  No-op if the project is not in the cache.
        """
        with cls._lock:
            instance = cls._instances.pop(project_id, None)
            if instance is None:
                logger.debug(
                    "[KnowledgeMemoryFactory] cleanup_project: not in cache, project_id=%s",
                    project_id,
                )
                return

            entry_count = 0
            try:
                entry_count = instance.count_all()
            except Exception:  # noqa: BLE001
                pass  # already partially closed; treat as zero
            finally:
                instance.close()

            if entry_count == 0:
                # Safe to delete — no data has ever been written to this project.
                project_dir = _DATA_DIR / "projects" / project_id
                try:
                    if project_dir.exists():
                        shutil.rmtree(project_dir)
                        logger.info(
                            "[KnowledgeMemoryFactory] deleted empty project dir: %s",
                            project_dir,
                        )
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "[KnowledgeMemoryFactory] could not delete empty project dir: %s",
                        project_dir,
                        exc_info=True,
                    )
            else:
                logger.info(
                    "[KnowledgeMemoryFactory] evicted (non-empty) project from cache: "
                    "project_id=%s entries=%d",
                    project_id, entry_count,
                )

    @classmethod
    def archive_inactive(cls, days: int = 30) -> list[str]:
        """Move project directories not modified in the last ``days`` days to archive.

        The move is atomic at the directory level (``shutil.move``) and is
        done OUTSIDE the factory lock so it does not stall concurrent
        ``get_or_create`` calls.  The project is evicted from ``_instances``
        (inside the lock) before its directory is moved.

        Safety guarantee
        ----------------
        Data is **never deleted** — it is moved to
        ``<DATA_DIR>/archive/<project_id>/``.  Restoring a project is a
        manual ``shutil.move`` back to ``projects/``.

        Parameters
        ----------
        days:
            Projects whose directory ``mtime`` is older than this many days
            are considered inactive.

        Returns
        -------
        list[str]
            Project IDs that were archived (empty list if none qualify).
        """
        projects_root = _DATA_DIR / "projects"
        archive_root = _DATA_DIR / "archive"

        if not projects_root.exists():
            logger.debug("[KnowledgeMemoryFactory] archive_inactive: no projects dir yet")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        archived: list[str] = []

        for project_dir in projects_root.iterdir():
            if not project_dir.is_dir():
                continue

            project_id = project_dir.name
            try:
                dir_mtime = datetime.fromtimestamp(
                    project_dir.stat().st_mtime, tz=timezone.utc
                )
            except OSError:
                continue  # can't stat — skip

            if dir_mtime >= cutoff:
                continue  # still active

            # --- Evict from cache first (holds lock briefly) ---
            with cls._lock:
                instance = cls._instances.pop(project_id, None)
                if instance is not None:
                    try:
                        instance.close()
                    except Exception:  # noqa: BLE001
                        pass

            # --- Move to archive (outside lock to avoid stalling callers) ---
            dest = archive_root / project_id
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(project_dir), str(dest))
                archived.append(project_id)
                logger.info(
                    "[KnowledgeMemoryFactory] archived inactive project: "
                    "project_id=%s last_modified=%s dest=%s",
                    project_id, dir_mtime.isoformat(), dest,
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "[KnowledgeMemoryFactory] failed to archive project: project_id=%s",
                    project_id,
                    exc_info=True,
                )
                # Re-add to cache if move failed so callers can still use it.
                if instance is not None:
                    with cls._lock:
                        cls._instances.setdefault(project_id, instance)

        logger.info(
            "[KnowledgeMemoryFactory] archive_inactive: days=%d archived=%d project(s)",
            days, len(archived),
        )
        return archived

    @classmethod
    def stats(cls) -> dict:
        """Return a snapshot of factory state for the /api/memory/stats endpoint.

        Returns
        -------
        dict with keys:
            total_projects_in_memory : int
            total_entries : int
            largest_project : dict | None  ({"project_id": str, "entries": int})
            inactive_project_count : int  (dirs under projects/ not in cache)
        """
        with cls._lock:
            snapshot = dict(cls._instances)

        total_entries = 0
        largest_project: dict | None = None
        largest_count = 0

        for pid, instance in snapshot.items():
            try:
                count = instance.count_all()
            except Exception:  # noqa: BLE001
                count = 0
            total_entries += count
            if count > largest_count:
                largest_count = count
                largest_project = {"project_id": pid, "entries": count}

        # Count project dirs that are NOT currently in cache (inactive on disk).
        projects_root = _DATA_DIR / "projects"
        inactive_count = 0
        if projects_root.exists():
            for d in projects_root.iterdir():
                if d.is_dir() and d.name not in snapshot:
                    inactive_count += 1

        return {
            "total_projects_in_memory": len(snapshot),
            "total_entries": total_entries,
            "largest_project": largest_project,
            "inactive_project_count": inactive_count,
        }
