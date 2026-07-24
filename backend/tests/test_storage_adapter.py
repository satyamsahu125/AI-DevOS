import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.storage.storage_adapter import MemoryStorageAdapter, StorageConfig, StorageQuery


class StorageAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = MemoryStorageAdapter(config=StorageConfig(driver="memory"))
        self.adapter.initialize()

    def test_connect_and_health(self) -> None:
        self.assertFalse(self.adapter.connection.connected)
        self.assertTrue(self.adapter.connect())
        self.assertTrue(self.adapter.connection.connected)
        health = self.adapter.health()
        self.assertTrue(health.healthy)
        self.assertEqual(health.metadata["driver"], "memory")

    def test_insert_select_count_delete(self) -> None:
        self.adapter.connect()
        result = self.adapter.insert("memory_records", {"memory_id": "m1", "content": "hello"})
        self.assertEqual(result.count, 1)
        self.assertEqual(result.inserted_id, "m1")

        rows = self.adapter.select(StorageQuery(table="memory_records", filters={"memory_id": "m1"}))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["content"], "hello")

        self.assertTrue(self.adapter.exists("memory_records", {"memory_id": "m1"}))
        self.assertEqual(self.adapter.count("memory_records", {}), 1)

        delete_result = self.adapter.delete("memory_records", {"memory_id": "m1"})
        self.assertEqual(delete_result.deleted, 1)
        self.assertFalse(self.adapter.exists("memory_records", {"memory_id": "m1"}))

    def test_update_records(self) -> None:
        self.adapter.connect()
        self.adapter.insert("memory_records", {"memory_id": "m2", "content": "hello"})
        result = self.adapter.update("memory_records", {"memory_id": "m2"}, {"content": "world"})
        self.assertEqual(result.updated, 1)
        rows = self.adapter.select(StorageQuery(table="memory_records", filters={"memory_id": "m2"}))
        self.assertEqual(rows[0]["content"], "world")

    def test_transactions(self) -> None:
        self.adapter.connect()
        trans = self.adapter.begin_transaction()
        self.assertTrue(trans.success)
        self.assertTrue(self.adapter.transaction.active)
        commit = self.adapter.commit()
        self.assertTrue(commit.success)
        self.assertFalse(self.adapter.transaction.active)

        rollback = self.adapter.begin_transaction()
        self.assertTrue(rollback.success)
        self.assertTrue(self.adapter.transaction.active)
        result = self.adapter.rollback()
        self.assertTrue(result.success)
        self.assertFalse(self.adapter.transaction.active)


if __name__ == "__main__":
    unittest.main()
