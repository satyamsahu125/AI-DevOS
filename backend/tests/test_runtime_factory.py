import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.runtime.agent_factory import AgentFactory
from app.shared.exceptions import DependencyException


class RuntimeFactoryTests(unittest.TestCase):
    def test_factory_creates_documented_agents(self) -> None:
        factory = AgentFactory()
        self.assertEqual(factory.create_product_owner().__class__.__name__, "ProductOwnerAgent")
        self.assertEqual(factory.create_architect().__class__.__name__, "ArchitectAgent")
        self.assertEqual(factory.create_backend().__class__.__name__, "BackendDeveloperAgent")
        self.assertEqual(factory.create_frontend().__class__.__name__, "FrontendDeveloperAgent")
        self.assertEqual(factory.create_qa().__class__.__name__, "QAAgent")
        self.assertEqual(factory.create_devops().__class__.__name__, "DevOpsAgent")

    def test_factory_rejects_unknown_agent(self) -> None:
        factory = AgentFactory()
        with self.assertRaises(DependencyException):
            factory.create("unknown")


if __name__ == "__main__":
    unittest.main()
