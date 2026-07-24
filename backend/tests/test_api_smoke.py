import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.agents.factory import AgentFactory
from app.api.dependencies import get_project_manager
from app.execution.manager import ExecutionManager
from app.main import app
from app.project.initializer import ProjectInitializer
from app.project.manager import ProjectManager
from app.shared.models.stage_artifact import StageArtifact
from app.workflow.engine import WorkflowEngine
from app.workflow.manager import WorkflowManager


class _StubProductOwnerAgent:
    """Fake ProductOwner agent used so this smoke test does not depend on a live Ollama server."""

    def execute(self, context: object) -> StageArtifact:
        content = getattr(context, "content", "")
        return StageArtifact(
            artifact_id="",
            name="product-owner-output",
            content=f"stub requirements for: {content}",
            status="Generated",
        )


class _StubLearningLoop:
    """Fake LearningLoop so tests don't load the real embedding model or touch its SQLite/HNSW files."""

    def get_relevant_patterns(self, task: str, stage: str, project_id: str = "", top_k: int = 3) -> list[str]:
        return []

    def record_trajectory(self, trajectory: object) -> None:
        return None


def _build_manager_with_stub_agent() -> ProjectManager:
    """Build a ProjectManager whose ProductOwner stage uses a stub agent instead of a real LLM call."""
    factory = AgentFactory()
    factory.registry.register("product_owner", _StubProductOwnerAgent())
    execution_manager = ExecutionManager(agent_factory=factory)
    workflow_engine = WorkflowEngine(execution_manager=execution_manager, learning_loop=_StubLearningLoop())
    workflow_manager = WorkflowManager(engine=workflow_engine)
    initializer = ProjectInitializer(workflow_manager=workflow_manager)
    return ProjectManager(initializer=initializer)


class APISmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides[get_project_manager] = _build_manager_with_stub_agent

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_project_manager, None)

    def test_health_and_project_routes(self) -> None:
        client = TestClient(app)

        health_response = client.get("/health")
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json(), {"status": "healthy"})

        project_response = client.post(
            "/projects",
            json={"name": "API Smoke", "description": "Smoke test project"},
        )
        self.assertEqual(project_response.status_code, 200)
        self.assertIn("project", project_response.json())
        self.assertTrue(project_response.json()["success"])


if __name__ == "__main__":
    unittest.main()
