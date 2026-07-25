import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.agents.factory import AgentFactory
from app.api.dependencies import get_artifact_manager, get_project_manager, get_workflow_manager, get_workspace_manager
from app.artifact.manager import ArtifactManager
from app.execution.manager import ExecutionManager
from app.main import app
from app.memory.manager import MemoryManager
from app.project.initializer import ProjectInitializer
from app.project.manager import ProjectManager
from app.project.repository import ProjectRepository
from app.shared.dto.project_request import ProjectRequest
from app.shared.enums.stage import Stage
from app.shared.models.stage_artifact import StageArtifact
from app.workflow.engine import WorkflowEngine
from app.workflow.manager import WorkflowManager
from app.workspace.manager import WorkspaceManager


class _EchoProductOwnerAgent:
    """Fake ProductOwner agent that echoes its input content, so two projects' outputs differ."""

    def execute(self, context: object) -> StageArtifact:
        content = getattr(context, "content", "")
        return StageArtifact(
            artifact_id="",
            name="product-owner-output",
            content=f"stub requirements for: {content}",
            status="Generated",
            structured_content={"summary": f"summary for {content}"},
        )


class _StubLearningLoop:
    """Fake LearningLoop so tests don't load the real embedding model or touch its SQLite/HNSW files."""

    def get_relevant_patterns(self, task: str, stage: str, project_id: str = "", top_k: int = 3) -> list[str]:
        return []

    def record_trajectory(self, trajectory: object) -> None:
        return None


class _IsolatedRig:
    """Builds a fully self-contained project stack rooted at a fresh temp directory:
    its own workspace root, artifact/memory SQLite files, and a stub ProductOwner
    agent -- so these tests never touch the shared backend/temp-workspace or
    backend/app/memory/memory.db the live app uses, and never call a real LLM."""

    def __init__(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="ai-devos-isolation-"))
        self.workspace_manager = WorkspaceManager(self.tmp_dir / "temp-workspace")
        self.artifact_manager = ArtifactManager(
            storage_dir=self.tmp_dir / "artifacts",
            workspace_manager=self.workspace_manager,
            db_path=self.tmp_dir / "memory.db",
        )
        self.memory_manager = MemoryManager(
            root=self.tmp_dir / "memory",
            repository=None,
        )
        factory = AgentFactory()
        factory.registry.register("product_owner", _EchoProductOwnerAgent())
        execution_manager = ExecutionManager(artifact_manager=self.artifact_manager, agent_factory=factory)
        self.workflow_engine = WorkflowEngine(
            execution_manager=execution_manager,
            memory_manager=self.memory_manager,
            learning_loop=_StubLearningLoop(),
            artifact_manager=self.artifact_manager,
            workspace_manager=self.workspace_manager,
        )
        self.workflow_manager = WorkflowManager(engine=self.workflow_engine)
        self.repository = ProjectRepository(root=self.tmp_dir / "projects")
        initializer = ProjectInitializer(workflow_manager=self.workflow_manager)
        self.project_manager = ProjectManager(repository=self.repository, initializer=initializer)
        self.project_manager.workspace_manager = self.workspace_manager

    def cleanup(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)


def _create_project_and_run_first_stage(rig: "_IsolatedRig", name: str, description: str) -> str:
    """Create a project, then explicitly run its ProductOwner stage.

    create_project() no longer runs any pipeline stage -- project creation
    must not depend on a reachable LLM -- so a test that needs a
    ProductOwner artifact has to ask for it, exactly as a real caller now
    does via POST /workflow/start. The content mirrors what
    ProjectInitializer used to send so name-in-artifact assertions still hold.
    """
    response = rig.project_manager.create_project(ProjectRequest(name=name, description=description))
    project_id = response.project.project_id
    rig.workflow_manager.run_stage(project_id, "ProductOwner", f"Build: {description}\n(Project name: {name})")
    return project_id


class ProjectIsolationTests(unittest.TestCase):
    def test_two_projects_dont_share_artifacts(self) -> None:
        rig = _IsolatedRig()
        try:
            id_a = _create_project_and_run_first_stage(rig, "Project A", "A")
            id_b = _create_project_and_run_first_stage(rig, "Project B", "B")

            path_a = rig.workspace_manager.get_artifact_path(id_a, Stage.ProductOwner.value)
            path_b = rig.workspace_manager.get_artifact_path(id_b, Stage.ProductOwner.value)
            self.assertTrue(path_a.exists())
            self.assertTrue(path_b.exists())
            self.assertIn(id_a, str(path_a))
            self.assertIn(id_b, str(path_b))

            content_a = path_a.read_text(encoding="utf-8")
            content_b = path_b.read_text(encoding="utf-8")
            self.assertNotEqual(content_a, content_b)
            self.assertIn("Project A", content_a)
            self.assertIn("Project B", content_b)
        finally:
            rig.cleanup()

    def test_memory_keys_isolated(self) -> None:
        rig = _IsolatedRig()
        try:
            rig.memory_manager.store("project-a", "requirements:latest", "requirements for A")
            rig.memory_manager.store("project-b", "requirements:latest", "requirements for B")

            self.assertEqual(rig.memory_manager.load("project-a", "requirements:latest"), "requirements for A")
            self.assertEqual(rig.memory_manager.load("project-b", "requirements:latest"), "requirements for B")
        finally:
            rig.cleanup()

    def test_artifact_history_preserved(self) -> None:
        rig = _IsolatedRig()
        try:
            rig.artifact_manager.save_artifact("proj-history", Stage.ProductOwner, "attempt one content", attempt=1)
            rig.artifact_manager.save_artifact("proj-history", Stage.ProductOwner, "attempt two content", attempt=2)
            rig.artifact_manager.mark_approved("proj-history", Stage.ProductOwner, 2)

            history = rig.artifact_manager.get_artifact_history("proj-history", Stage.ProductOwner)
            self.assertEqual(len(history), 2)
            self.assertEqual({item.attempt for item in history}, {1, 2})

            self.assertFalse(rig.artifact_manager.is_approved("proj-history", Stage.ProductOwner, 1))
            self.assertTrue(rig.artifact_manager.is_approved("proj-history", Stage.ProductOwner, 2))

            artifacts_dir = rig.workspace_manager.get_workspace_path("proj-history") / "artifacts"
            self.assertTrue((artifacts_dir / "ProductOwner.attempt-1.json").exists())
            self.assertTrue((artifacts_dir / "ProductOwner.attempt-2.json").exists())
        finally:
            rig.cleanup()

    def test_get_artifact(self) -> None:
        rig = _IsolatedRig()
        try:
            project_id = _create_project_and_run_first_stage(rig, "Get Artifact Test", "d")

            artifact = rig.artifact_manager.get_artifact(project_id, Stage.ProductOwner)
            self.assertIsNotNone(artifact)
            self.assertIn("Get Artifact Test", artifact.content)
            self.assertIn("summary", artifact.structured_content)
        finally:
            rig.cleanup()

    def test_project_status_endpoint(self) -> None:
        rig = _IsolatedRig()
        try:
            app.dependency_overrides[get_project_manager] = lambda: rig.project_manager
            app.dependency_overrides[get_workflow_manager] = lambda: rig.workflow_manager
            app.dependency_overrides[get_workspace_manager] = lambda: rig.workspace_manager
            app.dependency_overrides[get_artifact_manager] = lambda: rig.artifact_manager
            client = TestClient(app)

            create_response = client.post("/projects", json={"name": "Status Endpoint Test", "description": "d"})
            self.assertEqual(create_response.status_code, 201)
            project_id = create_response.json()["project"]["project_id"]

            # Creation no longer runs a stage, so drive the first stage explicitly
            # before asserting on stage progress.
            rig.workflow_manager.run_stage(project_id, "ProductOwner", "Build: d\n(Project name: Status Endpoint Test)")

            detail_response = client.get(f"/projects/{project_id}")
            self.assertEqual(detail_response.status_code, 200)
            detail = detail_response.json()
            self.assertIn(Stage.ProductOwner.value, detail["stages_completed"])
            self.assertEqual(detail["current_stage"], Stage.ProductOwner.value)
            self.assertEqual(len(detail["artifacts"]), 1)
        finally:
            app.dependency_overrides.pop(get_project_manager, None)
            app.dependency_overrides.pop(get_workflow_manager, None)
            app.dependency_overrides.pop(get_workspace_manager, None)
            app.dependency_overrides.pop(get_artifact_manager, None)
            rig.cleanup()


if __name__ == "__main__":
    unittest.main()
