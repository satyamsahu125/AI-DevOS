import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.backend import BackendDeveloperAgent
from app.agents.product_owner import ProductOwnerAgent


class AgentPromptTests(unittest.TestCase):
    def test_product_owner_agent_uses_role_specific_prompt(self) -> None:
        agent = ProductOwnerAgent()
        artifact = agent.execute(SimpleNamespace(content="build a CRM app"))

        self.assertIn("Product Owner", artifact.content)
        self.assertIn("build a CRM app", artifact.content)

    def test_backend_agent_uses_role_specific_prompt(self) -> None:
        agent = BackendDeveloperAgent()
        artifact = agent.execute(SimpleNamespace(content="create an API"))

        self.assertIn("Backend Developer", artifact.content)
        self.assertIn("create an API", artifact.content)


if __name__ == "__main__":
    unittest.main()
