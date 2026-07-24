import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.factory import AgentFactory
from app.agents.file_planner import FileStructurePlannerAgent
from app.artifact.manager import ArtifactManager
from app.llm.response import LLMResponse
from app.shared.enums.stage import Stage
from app.shared.schemas.file_plan_schema import FilePlanArtifact
from app.workflow.dependency_graph import DependencyGraph
from app.workspace.manager import WorkspaceManager


class _StubLLMManager:
    """Fake LLMManager that returns fixed content and records the last prompt it was called with."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.last_prompt: str | None = None

    def generate_text(self, prompt: str, system_prompt: str = "", **kwargs) -> LLMResponse:
        self.last_prompt = prompt
        return LLMResponse(content=self._content, model="stub", finish_reason="stop", input_tokens=0, output_tokens=0, total_tokens=0)


_PLAN_JSON = """{
  "files": [
    {"path": "main.py", "module": "api", "purpose": "entry point", "responsible_stage": "backend"},
    {"path": "src/App.jsx", "module": "ui", "purpose": "root component", "responsible_stage": "frontend"}
  ]
}"""


class FileStructurePlannerRegistrationTests(unittest.TestCase):
    def test_registered_under_both_registry_key_and_stage_name(self) -> None:
        factory = AgentFactory()
        self.assertIsInstance(factory.create("file_planner"), FileStructurePlannerAgent)
        self.assertIsInstance(factory.create("FileStructurePlanner"), FileStructurePlannerAgent)

    def test_appears_between_security_and_backend_in_stage_order(self) -> None:
        order = DependencyGraph.STAGE_ORDER
        self.assertLess(order.index("security"), order.index("file_planner"))
        self.assertLess(order.index("file_planner"), order.index("backend"))

    def test_backend_and_frontend_depend_on_file_planner(self) -> None:
        self.assertIn(Stage.FileStructurePlanner, DependencyGraph.STAGE_DEPENDENCIES[Stage.BackendDeveloper])
        self.assertIn(Stage.FileStructurePlanner, DependencyGraph.STAGE_DEPENDENCIES[Stage.FrontendDeveloper])
        # Existing Security/Designer deps must survive the addition (see test_designer_agent.py's
        # equivalent containment check for the same list).
        self.assertIn(Stage.Security, DependencyGraph.STAGE_DEPENDENCIES[Stage.FrontendDeveloper])
        self.assertIn(Stage.Designer, DependencyGraph.STAGE_DEPENDENCIES[Stage.FrontendDeveloper])


class FileStructurePlannerActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="file_planner_test_"))
        self.workspace_manager = WorkspaceManager(self.tmp_dir / "temp-workspace")
        self.artifact_manager = ArtifactManager(
            storage_dir=self.tmp_dir / "artifacts", workspace_manager=self.workspace_manager, db_path=self.tmp_dir / "memory.db",
        )
        self.workspace_manager.create_workspace("proj1")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_produces_structured_file_plan_and_injects_architecture(self) -> None:
        self.artifact_manager.save_artifact(
            "proj1", Stage.Architect, "arch content",
            structured_content={
                "approach": "modular monolith", "modules": [],
                "api_design": [{"path": "/tasks", "method": "GET", "request": "", "response": ""}],
                "data_models": [], "tech_stack": {},
            },
            attempt=1,
        )
        llm = _StubLLMManager(_PLAN_JSON)
        agent = FileStructurePlannerAgent(llm_manager=llm, artifact_manager=self.artifact_manager)

        artifact = agent.execute(SimpleNamespace(content="build a todo app", project_id="proj1"))

        self.assertEqual(artifact.schema_type, "WriteFilePlan")
        plan = FilePlanArtifact.model_validate(artifact.structured_content)
        self.assertEqual({f.path for f in plan.files}, {"main.py", "src/App.jsx"})
        self.assertIn("Architecture Summary", llm.last_prompt)
        self.assertIn("/tasks", llm.last_prompt)

    def test_no_project_id_omits_architecture_but_does_not_crash(self) -> None:
        llm = _StubLLMManager(_PLAN_JSON)
        agent = FileStructurePlannerAgent(llm_manager=llm, artifact_manager=self.artifact_manager)

        artifact = agent.execute(SimpleNamespace(content="build a todo app"))

        self.assertEqual(artifact.name, "file_plan")
        self.assertNotIn("Architecture Summary", llm.last_prompt)


if __name__ == "__main__":
    unittest.main()
