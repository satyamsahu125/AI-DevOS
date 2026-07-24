import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.factory import AgentFactory
from app.execution.manager import ExecutionManager
from app.project.initializer import ProjectInitializer
from app.project.manager import ProjectManager
from app.shared.dto.project_request import ProjectRequest
from app.shared.models.stage_artifact import StageArtifact
from app.workflow.engine import WorkflowEngine
from app.workflow.manager import WorkflowManager


class _StubProductOwnerAgent:
    """Fake ProductOwner agent used so project creation does not depend on a live Ollama server."""

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


class ProjectFlowTests(unittest.TestCase):
    def test_create_project_initializes_workspace_and_memory(self) -> None:
        manager = _build_manager_with_stub_agent()
        response = manager.create_project(ProjectRequest(name="Demo Project", description="Demo"))
        self.assertEqual(response.name, "Demo Project")
        self.assertTrue(Path(response.workspace_path).exists())


if __name__ == "__main__":
    unittest.main()
