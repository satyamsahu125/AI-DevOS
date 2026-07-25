import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.agents.architect import ArchitectAgent
from app.agents.document import DocumentAgent
from app.agents.factory import AgentFactory
from app.agents.retro import RetroAgent
from app.agents.security import SecurityAgent
from app.agents.strategic_review import StrategicReviewAgent
from app.api.dependencies import (
    get_artifact_manager,
    get_knowledge_memory,
    get_learning_loop,
    get_llm_manager,
    get_memory_manager,
    get_project_manager,
    get_workflow_manager,
    get_workspace_manager,
)
from app.artifact.manager import ArtifactManager
from app.execution.manager import ExecutionManager
from app.llm.response import LLMResponse
from app.main import app
from app.memory.learning_loop import LearningLoop, Trajectory
from app.memory.manager import MemoryManager
from app.project.initializer import ProjectInitializer
from app.project.manager import ProjectManager
from app.project.repository import ProjectRepository
from app.shared.dto.project_request import ProjectRequest
from app.shared.enums.project_state import ProjectState
from app.shared.enums.stage import Stage
from app.shared.models.stage_artifact import StageArtifact
from app.workflow.dependency_graph import DependencyGraph
from app.workflow.engine import WorkflowEngine
from app.workflow.manager import WorkflowManager
from app.workflow.retry_policy import RetryPolicy
from app.workspace.manager import WorkspaceManager


class _StubLLMManager:
    """Fake LLMManager that echoes the prompt as the response content (no live Ollama needed)."""

    def __init__(self) -> None:
        self.last_prompt: str | None = None

    def generate_text(self, prompt: str, system_prompt: str = "", model: str | None = None, **kwargs) -> LLMResponse:
        self.last_prompt = prompt
        return LLMResponse(content=prompt, model="stub-model", finish_reason="stop", input_tokens=0, output_tokens=0, total_tokens=0)


class _StageEchoAgent:
    """Fake stage agent that echoes its input content, used to drive the full pipeline without an LLM."""

    def __init__(self, name: str) -> None:
        self._name = name

    def execute(self, context: object) -> StageArtifact:
        content = getattr(context, "content", "")
        return StageArtifact(artifact_id="", name=self._name, content=f"{self._name} output for: {content}", status="Generated")


class _FlakyAgent:
    """Fails Reviewer's ASK_HUMAN schema check for the first fail_times calls, then produces a good artifact."""

    def __init__(self, fail_times: int = 1) -> None:
        self.calls = 0
        self.fail_times = fail_times
        self.received_contents: list[str] = []

    def execute(self, context: object) -> StageArtifact:
        content = getattr(context, "content", "")
        self.received_contents.append(content)
        self.calls += 1
        if self.calls <= self.fail_times:
            return StageArtifact(artifact_id="", name="x", content="short", schema_type="TestSchema", structured_content={})
        return StageArtifact(
            artifact_id="", name="x", content="a properly long and complete artifact body describing the work",
            schema_type="TestSchema", structured_content={"ok": True},
        )


class _StubLearningLoop:
    def get_relevant_patterns(self, task, stage, project_id="", top_k=3):
        return []

    def record_trajectory(self, trajectory):
        return None


def _build_pipeline_manager(tmp_dir: Path, retry_policy: RetryPolicy | None = None) -> tuple[WorkflowManager, WorkspaceManager, ArtifactManager]:
    """Build a fully isolated WorkflowManager wired with one echo agent per registered stage."""
    workspace_manager = WorkspaceManager(tmp_dir / "temp-workspace")
    artifact_manager = ArtifactManager(storage_dir=tmp_dir / "artifacts", workspace_manager=workspace_manager, db_path=tmp_dir / "memory.db")
    factory = AgentFactory()
    for stage_key in factory.registry.agents:
        factory.registry.register(stage_key, _StageEchoAgent(stage_key))
    execution_manager = ExecutionManager(artifact_manager=artifact_manager, agent_factory=factory)
    engine = WorkflowEngine(
        execution_manager=execution_manager,
        memory_manager=MemoryManager(root=tmp_dir / "memory"),
        learning_loop=_StubLearningLoop(),
        artifact_manager=artifact_manager,
        workspace_manager=workspace_manager,
        retry_policy=retry_policy,
    )
    return WorkflowManager(engine=engine), workspace_manager, artifact_manager


class Fix001ArchitectRegistrationTests(unittest.TestCase):
    def test_architect_agent_is_registered_and_creatable(self) -> None:
        factory = AgentFactory()
        agent = factory.create("Architect")
        self.assertIsInstance(agent, ArchitectAgent)

    def test_architect_resolves_from_lowercase_registry_key(self) -> None:
        factory = AgentFactory()
        agent = factory.create("architect")
        self.assertIsInstance(agent, ArchitectAgent)


class Fix002MultiStagePipelineTests(unittest.TestCase):
    def test_pipeline_runs_every_stage_in_order(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="fix002_"))
        try:
            manager, workspace_manager, _ = _build_pipeline_manager(tmp_dir)
            workspace_manager.create_workspace("proj-pipeline")
            result = manager.run("proj-pipeline", "Build a todo app")
            if getattr(result, "requires_user_action", False):
                workspace_manager.update_design_review("proj-pipeline", "approved", "Auto-approved for test")
                workspace_manager.update_state("proj-pipeline", ProjectState.DESIGN_APPROVED)
                result = manager.run("proj-pipeline", "Build a todo app")

            expected = [s.value for s in DependencyGraph.ordered_stages()]
            self.assertEqual(result.completed_stages, expected)
            self.assertTrue(result.success)
            self.assertIsNone(result.failed_stage)

            project_json = workspace_manager.load_project_json("proj-pipeline")
            self.assertEqual(project_json["stages_completed"], expected)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_dependency_graph_next_stage_and_dependencies(self) -> None:
        self.assertEqual(DependencyGraph.get_next_stage(Stage.StrategicReview), Stage.ProductOwner)
        self.assertEqual(DependencyGraph.get_next_stage(Stage.Retro), None)
        self.assertEqual(DependencyGraph.get_stage_dependencies(Stage.Designer), [Stage.Architect])


class Fix003UnstubbedAgentsTests(unittest.TestCase):
    def _assert_llm_backed(self, agent) -> None:
        artifact = agent.execute(SimpleNamespace(content="do the thing"))
        self.assertIn("do the thing", artifact.content)
        self.assertNotIn("not yet implemented", artifact.content)

    def test_strategic_review_agent_calls_llm(self) -> None:
        self._assert_llm_backed(StrategicReviewAgent(llm_manager=_StubLLMManager()))

    def test_security_agent_calls_llm(self) -> None:
        self._assert_llm_backed(SecurityAgent(llm_manager=_StubLLMManager()))

    def test_document_agent_calls_llm(self) -> None:
        self._assert_llm_backed(DocumentAgent(llm_manager=_StubLLMManager()))

    def test_retro_agent_calls_llm(self) -> None:
        self._assert_llm_backed(RetroAgent(llm_manager=_StubLLMManager()))


class Fix004And005ReviewerAndRetryTests(unittest.TestCase):
    def test_real_reviewer_rejects_then_retry_injects_feedback_and_approves(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="fix004_"))
        try:
            workspace_manager = WorkspaceManager(tmp_dir / "temp-workspace")
            artifact_manager = ArtifactManager(storage_dir=tmp_dir / "artifacts", workspace_manager=workspace_manager, db_path=tmp_dir / "memory.db")
            factory = AgentFactory()
            flaky = _FlakyAgent(fail_times=1)
            factory.registry.register("product_owner", flaky)
            execution_manager = ExecutionManager(artifact_manager=artifact_manager, agent_factory=factory)
            engine = WorkflowEngine(
                execution_manager=execution_manager,
                memory_manager=MemoryManager(root=tmp_dir / "memory"),
                learning_loop=_StubLearningLoop(),
                artifact_manager=artifact_manager,
                workspace_manager=workspace_manager,
                retry_policy=RetryPolicy(max_retries=3),
            )
            result = engine.run("proj-retry", "ProductOwner", "initial task")

            self.assertTrue(result.success)
            self.assertEqual(flaky.calls, 2)
            self.assertNotIn("REVIEWER FEEDBACK", flaky.received_contents[0])
            self.assertIn("REVIEWER FEEDBACK", flaky.received_contents[1])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_retry_policy_default_is_three(self) -> None:
        self.assertEqual(RetryPolicy().max_retries, 3)


class Fix006ReadyEndpointTests(unittest.TestCase):
    class _FakeLLMManager:
        def __init__(self, reachable: bool, model_available: bool) -> None:
            self._reachable = reachable
            self._model_available = model_available
            self.configured_model = "qwen2.5-coder:7b"

        def health(self):
            return SimpleNamespace(reachable=self._reachable)

        def is_model_available(self) -> bool:
            return self._model_available

    def setUp(self) -> None:
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_llm_manager, None)

    def test_ready_returns_200_when_healthy(self) -> None:
        app.dependency_overrides[get_llm_manager] = lambda: self._FakeLLMManager(True, True)
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["ollama"], "reachable")
        self.assertTrue(body["model_available"])

    def test_ready_returns_503_when_ollama_unreachable(self) -> None:
        app.dependency_overrides[get_llm_manager] = lambda: self._FakeLLMManager(False, False)
        response = self.client.get("/ready")
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["ollama"], "unreachable")


class Fix007NewEndpointsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="fix007_"))
        self.workspace_manager = WorkspaceManager(self.tmp_dir / "temp-workspace")
        self.artifact_manager = ArtifactManager(storage_dir=self.tmp_dir / "artifacts", workspace_manager=self.workspace_manager, db_path=self.tmp_dir / "memory.db")
        self.memory_manager = MemoryManager(root=self.tmp_dir / "memory")
        factory = AgentFactory()
        factory.registry.register("product_owner", _StageEchoAgent("product_owner"))
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

        app.dependency_overrides[get_project_manager] = lambda: self.project_manager
        app.dependency_overrides[get_workflow_manager] = lambda: self.workflow_manager
        app.dependency_overrides[get_workspace_manager] = lambda: self.workspace_manager
        app.dependency_overrides[get_artifact_manager] = lambda: self.artifact_manager
        app.dependency_overrides[get_memory_manager] = lambda: self.memory_manager
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for dep in (get_project_manager, get_workflow_manager, get_workspace_manager, get_artifact_manager, get_memory_manager):
            app.dependency_overrides.pop(dep, None)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_project(self, name: str, description: str) -> str:
        """Create a project and run its first stage.

        POST /projects deliberately no longer runs a pipeline stage (creation
        must not depend on a reachable LLM), so the ProductOwner artifact these
        endpoint tests inspect has to be produced by an explicit stage run --
        the same thing a real caller now does via POST /workflow/start.
        """
        response = self.client.post("/projects", json={"name": name, "description": description})
        self.assertEqual(response.status_code, 201)
        project_id = response.json()["project"]["project_id"]
        self.workflow_manager.run_stage(project_id, "ProductOwner", f"Build: {description}\n(Project name: {name})")
        return project_id

    def test_list_and_get_artifact_endpoints(self) -> None:
        project_id = self._create_project("Artifacts Test", "Build a widget")

        listing = self.client.get(f"/artifacts/{project_id}")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()), 1)

        detail = self.client.get(f"/artifacts/{project_id}/product_owner")
        self.assertEqual(detail.status_code, 200)
        self.assertIn("Build a widget", detail.json()["content"])

        history = self.client.get(f"/artifacts/{project_id}/product_owner/history")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.json()), 1)
        self.assertTrue(history.json()[0]["approved"])

    def test_get_artifact_404_for_unknown_stage_output(self) -> None:
        project_id = self._create_project("Artifacts 404 Test", "Build a widget")
        response = self.client.get(f"/artifacts/{project_id}/qa")
        self.assertEqual(response.status_code, 404)

    def test_agents_endpoint_reports_all_llm_backed(self) -> None:
        response = self.client.get("/agents")
        self.assertEqual(response.status_code, 200)
        agents = response.json()
        self.assertEqual(len(agents), 14)
        self.assertTrue(all(agent["llm_backed"] for agent in agents))

    def test_memory_endpoint_returns_project_records(self) -> None:
        project_id = self._create_project("Memory Test", "Build a widget")
        response = self.client.get(f"/memory/{project_id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["project_id"], project_id)
        self.assertTrue(any(record["key"] == "workflow:latest_message" for record in body["records"]))

    def test_delete_project_removes_workspace_and_record(self) -> None:
        project_id = self._create_project("Delete Test", "Build a widget")
        workspace_path = self.workspace_manager.get_workspace_path(project_id)
        self.assertTrue(workspace_path.exists())

        delete_response = self.client.delete(f"/projects/{project_id}")
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(workspace_path.exists())
        self.assertFalse(self.repository.exists(project_id))

        get_response = self.client.get(f"/projects/{project_id}")
        self.assertEqual(get_response.status_code, 404)

    def test_delete_unknown_project_404s(self) -> None:
        response = self.client.delete("/projects/does-not-exist")
        self.assertEqual(response.status_code, 404)


class BugFixDescriptionAndPatternLeakTests(unittest.TestCase):
    def test_project_initializer_sends_description_not_just_name(self) -> None:
        received = {}

        class _RecordingWorkflowManager:
            def run_stage(self, project_id, stage_name, content):
                received["content"] = content
                return SimpleNamespace(success=True, message="ok")

        initializer = ProjectInitializer(workflow_manager=_RecordingWorkflowManager())
        project = SimpleNamespace(project_id="p1", name="calci", description="Create a basic calculator app")
        initializer.initialize(project)

        self.assertIn("Create a basic calculator app", received["content"])

    def test_pattern_search_is_isolated_per_project(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="pattern_leak_"))
        try:
            from app.memory.knowledge_memory import KnowledgeMemory

            knowledge_memory = KnowledgeMemory(db_path=tmp_dir / "knowledge.db", index_path=tmp_dir / "knowledge.hnsw", max_elements=50)
            loop = LearningLoop(knowledge_memory=knowledge_memory, db_path=tmp_dir / "learning.db")

            loop.record_trajectory(Trajectory(
                stage="ProductOwner", task_description="Create a basic calculator app",
                artifact_summary="InvoiceMaster: invoicing app for freelancers",
                retry_count=0, approved=True, reviewer_feedback="", agent_model="m",
                tokens_used=0, latency_ms=0.0, project_id="project-a",
            ))

            patterns_for_b = loop.get_relevant_patterns("Create a basic calculator app", "ProductOwner", project_id="project-b")
            patterns_for_a = loop.get_relevant_patterns("Create a basic calculator app", "ProductOwner", project_id="project-a")

            self.assertEqual(patterns_for_b, [])
            self.assertEqual(len(patterns_for_a), 1)
            self.assertIn("InvoiceMaster", patterns_for_a[0])
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
