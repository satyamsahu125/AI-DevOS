import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.base_agent import BaseAgent
from app.agents.product_owner import ProductOwnerAgent
from app.artifact.manager import ArtifactManager
from app.execution.execution_result import ExecutionResult
from app.llm.provider import BaseLLMProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.request import LLMRequest
from app.llm.response import LLMResponse
from app.prompt.builder import PromptBuilder
from app.prompt.product_owner_builder import ProductOwnerPromptBuilder
from app.review.reviewer import Reviewer
from app.shared.models.architecture_artifact import ArchitectureArtifact
from app.workflow.transition import WorkflowTransition


class DocumentedArchitectureTests(unittest.TestCase):
    def test_documented_runtime_components_are_importable(self) -> None:
        self.assertTrue(issubclass(ProductOwnerAgent, BaseAgent))
        self.assertTrue(issubclass(OllamaProvider, BaseLLMProvider))

        request = LLMRequest(system_prompt="sys", user_prompt="user", model="test", temperature=0.0, max_tokens=16, stream=False)
        response = LLMResponse(content="ok", model="test", finish_reason="stop", input_tokens=1, output_tokens=1, total_tokens=2)
        self.assertEqual(request.model, "test")
        self.assertEqual(response.content, "ok")

        builder = PromptBuilder()
        self.assertTrue(callable(builder.build))

        artifact_manager = ArtifactManager(storage_dir=Path(__file__).resolve().parent / "tmp-artifacts")
        artifact = artifact_manager.create_artifact("requirements", "content")
        self.assertEqual(artifact.name, "requirements")

        result = ExecutionResult(success=True, artifact=artifact, error=None, execution_time=0.0)
        self.assertTrue(result.success)

        reviewer = Reviewer()
        self.assertTrue(callable(reviewer.review))

        transition = WorkflowTransition()
        self.assertTrue(callable(transition.transition))

        architecture = ArchitectureArtifact(
            artifact_id="arch-1",
            name="architecture",
            version=1,
            status="Generated",
            created_at=None,
            approved_at=None,
            location=Path("/tmp/architecture.md"),
            content="# Architecture",
            author="system",
            reviewer=None,
            metadata={},
        )
        self.assertEqual(architecture.version, 1)


if __name__ == "__main__":
    unittest.main()
