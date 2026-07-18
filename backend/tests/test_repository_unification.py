import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.artifacts.manager import ArtifactManager as UnifiedArtifactManager
from app.context.context import ContextBuilder
from app.core.exceptions import ConfigurationException, DependencyException
from app.llm.manager import LLMManager
from app.memory.manager import MemoryManager
from app.session.manager import SessionManager


class RepositoryUnificationTests(unittest.TestCase):
    def test_unified_packages_are_importable(self) -> None:
        self.assertTrue(callable(UnifiedArtifactManager))
        self.assertTrue(callable(getattr(ContextBuilder, "__init__", None)))
        self.assertTrue(callable(LLMManager))
        self.assertTrue(callable(MemoryManager))
        self.assertTrue(callable(SessionManager))

    def test_core_exceptions_are_available(self) -> None:
        self.assertTrue(issubclass(ConfigurationException, Exception))
        self.assertTrue(issubclass(DependencyException, Exception))


if __name__ == "__main__":
    unittest.main()
