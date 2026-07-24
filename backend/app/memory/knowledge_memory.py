from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import hnswlib
import numpy as np

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 384
_MODEL_NAME = "all-MiniLM-L6-v2"
_DEFAULT_MAX_ELEMENTS = 1000

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "memory" / "knowledge.db"
_DEFAULT_INDEX_PATH = Path(__file__).resolve().parents[1] / "memory" / "knowledge.hnsw"

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
        """
        with self._lock:
            logger.debug("store: key=%s category=%s", key, category)
            existing_id = self._get_id_by_key(key)
            if existing_id is not None:
                self._delete_by_id(existing_id, key)

            embedding = self._embed(value)
            cursor = self._conn.execute(
                "INSERT INTO knowledge_entries (key, value, category, source, created_at) VALUES (?, ?, ?, ?, ?)",
                (key, value, category, source, datetime.now(timezone.utc).isoformat()),
            )
            self._conn.commit()
            entry_id = cursor.lastrowid

            self._ensure_capacity(1)
            self._index.add_items(embedding.reshape(1, -1), np.array([entry_id]))
            self._save_index()

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
