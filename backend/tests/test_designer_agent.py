import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.execution.manager import ExecutionManager
from app.memory.knowledge_memory import KnowledgeMemory
from app.memory.learning_loop import LearningLoop
from app.memory.manager import MemoryManager
from app.review.reviewer import ReviewTier, Reviewer
from app.shared.enums.stage import Stage
from app.shared.models.stage_artifact import StageArtifact
from app.shared.schemas.design_schema import DesignArtifact, UIComponent, UserFlow
from app.workflow.dependency_graph import DependencyGraph
from app.workflow.engine import WorkflowEngine


class _StubLearningLoop:
    def get_relevant_patterns(self, task, stage, project_id="", top_k=3):
        return []

    def record_trajectory(self, trajectory):
        return None


class DesignSchemaTests(unittest.TestCase):
    def test_design_artifact_schema_validates_correctly(self) -> None:
        artifact = DesignArtifact(
            project_name="Demo",
            design_system={"colors": {"primary": "#000"}, "fonts": {"body": "Inter"}, "spacing": {"unit": "8px"}, "breakpoints": {"mobile": "0px"}},
            user_flows=[
                UserFlow(name="Login", steps=["enter email", "enter password", "submit"], entry_point="/login", success_end="/dashboard", error_end="/login?error"),
            ],
            components=[
                UIComponent(name="LoginForm", type="form", purpose="authenticate user", inputs=["email", "password"], outputs=["session token"], states=["loading", "error", "empty", "populated"]),
            ],
            page_layouts=[{"login": ["LoginForm"]}],
            api_dependencies=["/api/auth/login"],
            accessibility_notes=["form fields have associated labels"],
        )

        restored = DesignArtifact.model_validate_json(artifact.model_dump_json())

        self.assertEqual(restored.project_name, "Demo")
        self.assertEqual(restored.user_flows[0].name, "Login")
        self.assertEqual(restored.components[0].type, "form")


class DependencyGraphTests(unittest.TestCase):
    def test_designer_appears_after_architect_before_security(self) -> None:
        order = DependencyGraph.STAGE_ORDER
        self.assertLess(order.index("architect"), order.index("designer"))
        self.assertLess(order.index("designer"), order.index("security"))

    def test_designer_appears_before_frontend(self) -> None:
        order = DependencyGraph.STAGE_ORDER
        self.assertLess(order.index("designer"), order.index("frontend"))

    def test_stage_dependencies_frontend_depends_on_designer_and_security(self) -> None:
        deps = DependencyGraph.STAGE_DEPENDENCIES[Stage.FrontendDeveloper]
        self.assertIn(Stage.Designer, deps)
        self.assertIn(Stage.Security, deps)

    def test_stage_dependencies_designer_depends_on_architect(self) -> None:
        self.assertEqual(DependencyGraph.STAGE_DEPENDENCIES[Stage.Designer], [Stage.Architect])


class FrontendContextIncludesDesignTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="designer_workflow_test_"))
        self.memory_manager = MemoryManager(root=self._tmp_dir / "memory")
        self.engine = WorkflowEngine(
            execution_manager=ExecutionManager(),
            memory_manager=self.memory_manager,
            learning_loop=_StubLearningLoop(),
        )

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_frontend_content_includes_approved_design_after_designer_approval(self) -> None:
        design_artifact = StageArtifact(
            artifact_id="d1", name="designer-output",
            content='{"project_name": "Demo", "components": [{"name": "LoginForm"}]}',
            schema_type="WriteDesign",
        )
        self.engine._record_design("proj-1", Stage.Designer, design_artifact)

        frontend_content = self.engine._with_design_context("proj-1", "Implement the login page", "FrontendDeveloper")

        self.assertIn("Approved Design Spec", frontend_content)
        self.assertIn("LoginForm", frontend_content)

    def test_qa_content_also_includes_approved_design(self) -> None:
        design_artifact = StageArtifact(artifact_id="d1", name="designer-output", content="design spec text", schema_type="WriteDesign")
        self.engine._record_design("proj-1", Stage.Designer, design_artifact)

        qa_content = self.engine._with_design_context("proj-1", "Write test cases", "QA")

        self.assertIn("design spec text", qa_content)

    def test_non_dependent_stage_does_not_receive_design_context(self) -> None:
        design_artifact = StageArtifact(artifact_id="d1", name="designer-output", content="design spec text", schema_type="WriteDesign")
        self.engine._record_design("proj-1", Stage.Designer, design_artifact)

        backend_content = self.engine._with_design_context("proj-1", "Implement the API", "BackendDeveloper")

        self.assertEqual(backend_content, "Implement the API")

    def test_no_design_recorded_yet_leaves_content_unchanged(self) -> None:
        content = self.engine._with_design_context("proj-1", "Implement the login page", "FrontendDeveloper")
        self.assertEqual(content, "Implement the login page")


class ReviewerRejectsDesignWithNoUserFlowsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="designer_reviewer_test_"))
        knowledge_memory = KnowledgeMemory(
            db_path=self._tmp_dir / "knowledge.db",
            index_path=self._tmp_dir / "knowledge.hnsw",
            max_elements=20,
        )
        learning_loop = LearningLoop(knowledge_memory=knowledge_memory, db_path=self._tmp_dir / "learning.db")
        self.reviewer = Reviewer(learning_loop=learning_loop)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _design_artifact(self, **structured_overrides) -> StageArtifact:
        structured = {
            "project_name": "Demo",
            "design_system": {"colors": {}, "fonts": {}, "spacing": {}, "breakpoints": {}},
            "user_flows": [],
            "components": [],
            "page_layouts": [{"home": ["Header"]}],
            "api_dependencies": [],
            "accessibility_notes": ["labels on all inputs"],
        }
        structured.update(structured_overrides)
        return StageArtifact(
            artifact_id="d1", name="designer-output",
            content="A design spec with no user flows defined.",
            schema_type="WriteDesign",
            structured_content=structured,
        )

    def test_reviewer_rejects_design_with_no_user_flows(self) -> None:
        result = self.reviewer.review(self._design_artifact(user_flows=[]))

        self.assertFalse(result.approved)
        self.assertTrue(any("dead end" in q or "flow" in q.lower() for q in result.human_questions) or any(f.tier == ReviewTier.FLAG for f in result.findings))

    def test_reviewer_flags_fewer_than_three_user_flows(self) -> None:
        result = self.reviewer.review(self._design_artifact(user_flows=[
            {"name": "Login", "steps": ["a"], "entry_point": "/login", "success_end": "/home", "error_end": "/login"},
        ]))

        self.assertTrue(any("user flow" in f.description.lower() for f in result.findings if f.tier == ReviewTier.FLAG))

    def test_reviewer_ask_human_on_dead_end_flow(self) -> None:
        result = self.reviewer.review(self._design_artifact(user_flows=[
            {"name": "Broken", "steps": ["a"], "entry_point": "", "success_end": "", "error_end": ""},
        ]))

        self.assertFalse(result.approved)
        self.assertTrue(any(f.tier == ReviewTier.ASK_HUMAN for f in result.findings))

    def test_reviewer_approves_well_formed_design(self) -> None:
        result = self.reviewer.review(self._design_artifact(
            user_flows=[
                {"name": "Login", "steps": ["a", "b"], "entry_point": "/login", "success_end": "/home", "error_end": "/login"},
                {"name": "Signup", "steps": ["a", "b"], "entry_point": "/signup", "success_end": "/home", "error_end": "/signup"},
                {"name": "Logout", "steps": ["a"], "entry_point": "/home", "success_end": "/login", "error_end": "/home"},
            ],
            components=[{"name": "LoginForm", "type": "form", "purpose": "auth", "inputs": [], "outputs": [], "states": ["loading", "error", "empty", "populated"]}],
        ))

        self.assertTrue(result.approved)


if __name__ == "__main__":
    unittest.main()
