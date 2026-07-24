import sys
import unittest
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory.memory_repository import MemoryRepository
from app.memory.repository_models import MemoryRecord
from app.memory.repository_query import RepositoryQuery
from app.shared.enums.memory_type import MemoryType


class MemoryRepositoryTests(unittest.TestCase):
    def test_save_and_load_round_trip(self) -> None:
        repo = MemoryRepository(storage=None)
        repo.initialize()
        record = MemoryRecord(
            memory_id=uuid4(),
            project_id=uuid4(),
            workflow_id=uuid4(),
            stage="planning",
            memory_type=MemoryType.Project,
            title="plan",
            content="hello world",
            tags=["alpha"],
        )

        saved = repo.save(record)
        loaded = repo.load(saved.memory_id)

        self.assertEqual(saved.memory_id, loaded.memory_id)
        self.assertEqual(1, loaded.version)

    def test_find_by_type_and_count(self) -> None:
        repo = MemoryRepository(storage=None)
        repo.initialize()
        record = MemoryRecord(
            memory_id=uuid4(),
            project_id=uuid4(),
            workflow_id=uuid4(),
            stage="planning",
            memory_type=MemoryType.Project,
            title="plan",
            content="hello world",
        )
        repo.save(record)

        results = repo.find(RepositoryQuery(memory_type=MemoryType.Project, limit=10))
        self.assertEqual(1, len(results))
        self.assertEqual(1, repo.count())


if __name__ == "__main__":
    unittest.main()
