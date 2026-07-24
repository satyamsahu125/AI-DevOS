import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory.knowledge_memory import KnowledgeMemory, SearchResult


class KnowledgeMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="knowledge_memory_test_"))
        self.km = KnowledgeMemory(
            db_path=self._tmp_dir / "knowledge.db",
            index_path=self._tmp_dir / "knowledge.hnsw",
            max_elements=20,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_search_on_empty_index_returns_empty_list(self) -> None:
        self.assertEqual(self.km.search("anything"), [])

    def test_store_and_search_returns_correct_results(self) -> None:
        self.km.store("sky", "The sky is blue due to Rayleigh scattering of sunlight.", category="science")
        self.km.store("python", "Python is a popular language for web development and data science.", category="tech")
        self.km.store("plants", "Photosynthesis converts sunlight into chemical energy in plants.", category="science")

        results = self.km.search("why does the sky look blue", top_k=1)

        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], SearchResult)
        self.assertEqual(results[0].key, "sky")
        self.assertEqual(results[0].category, "science")

    def test_search_respects_category_filter(self) -> None:
        self.km.store("sky", "The sky is blue due to Rayleigh scattering of sunlight.", category="science")
        self.km.store("python", "Python is a popular language for web development.", category="tech")

        results = self.km.search("programming languages", top_k=5, category_filter="tech")

        self.assertEqual([r.key for r in results], ["python"])

    def test_get_by_key_returns_stored_value_or_none(self) -> None:
        self.km.store("fact", "A stored fact.", category="general")

        self.assertEqual(self.km.get_by_key("fact"), "A stored fact.")
        self.assertIsNone(self.km.get_by_key("missing"))

    def test_delete_removes_entry_from_storage_and_search(self) -> None:
        self.km.store("fact1", "The sky is blue due to Rayleigh scattering.", category="science")
        self.km.store("fact2", "Photosynthesis converts sunlight into energy.", category="science")

        self.assertTrue(self.km.delete("fact1"))
        self.assertFalse(self.km.delete("fact1"))  # already gone
        self.assertIsNone(self.km.get_by_key("fact1"))

        results = self.km.search("Rayleigh scattering sky", top_k=5)
        self.assertNotIn("fact1", [r.key for r in results])

    def test_store_under_existing_key_replaces_it(self) -> None:
        self.km.store("fact", "original value", category="general")
        self.km.store("fact", "updated value", category="general")

        self.assertEqual(self.km.get_by_key("fact"), "updated value")

    def test_auto_grows_index_past_initial_max_elements(self) -> None:
        for i in range(30):  # more than max_elements=20
            self.km.store(f"item{i}", f"generic fact number {i} about widgets", category="auto")

        self.assertGreaterEqual(self.km._index.get_current_count(), 30)
        results = self.km.search("widgets", top_k=5)
        self.assertGreater(len(results), 0)

    def test_persistence_store_reload_index_search_still_works(self) -> None:
        self.km.store("sky", "The sky is blue due to Rayleigh scattering of sunlight.", category="science")
        self.km.store("python", "Python is a popular language for web development.", category="tech")

        reloaded = KnowledgeMemory(
            db_path=self._tmp_dir / "knowledge.db",
            index_path=self._tmp_dir / "knowledge.hnsw",
            max_elements=20,
        )

        self.assertEqual(reloaded.get_by_key("sky"), "The sky is blue due to Rayleigh scattering of sunlight.")
        results = reloaded.search("why is the sky blue", top_k=1)
        self.assertEqual(results[0].key, "sky")


if __name__ == "__main__":
    unittest.main()
