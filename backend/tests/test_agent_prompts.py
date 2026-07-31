import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.backend import BackendDeveloperAgent
from app.agents.product_owner import ProductOwnerAgent
from app.llm.response import LLMResponse


class _StubLLMManager:
    """Fake LLMManager that echoes the prompt it was called with as the response content.

    Used so agent tests exercise the real execute() -> prompt_builder -> LLMManager
    wiring without depending on a live Ollama server.
    """

    def __init__(self) -> None:
        self.last_prompt: str | None = None
        self.last_system_prompt: str | None = None

    def generate_text(self, prompt: str, system_prompt: str = "", model: str | None = None, **kwargs) -> LLMResponse:
        self.last_prompt = prompt
        self.last_system_prompt = system_prompt
        return LLMResponse(
            content=prompt,
            model="stub-model",
            finish_reason="stop",
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )


class AgentPromptTests(unittest.TestCase):
    def test_product_owner_agent_uses_role_specific_prompt(self) -> None:
        llm = _StubLLMManager()
        agent = ProductOwnerAgent(llm_manager=llm)
        from app.execution.exceptions import SchemaValidationError
        with self.assertRaises(SchemaValidationError):
            agent.execute(SimpleNamespace(content="build a CRM app"))

        self.assertIn("Product Manager", llm.last_prompt)
        self.assertIn("build a CRM app", llm.last_prompt)

    def test_backend_agent_without_a_file_plan_produces_an_empty_manifest(self) -> None:
        """No FileStructurePlanner output exists for this ad-hoc call (no project_id, no seeded
        File Plan) -- BackendDeveloperAgent must respond gracefully with a valid manifest artifact
        instead of crashing or calling the LLM with nothing to generate. Per-file prompt wiring
        against a real File Plan is covered in test_project_file_generation.py."""
        llm = _StubLLMManager()
        agent = BackendDeveloperAgent(llm_manager=llm)
        artifact = agent.execute(SimpleNamespace(content="create an API"))

        self.assertIn("Backend Developer", artifact.content)
        self.assertEqual(artifact.structured_content["planned_paths"], [])
        self.assertIsNone(llm.last_prompt)


if __name__ == "__main__":
    unittest.main()
