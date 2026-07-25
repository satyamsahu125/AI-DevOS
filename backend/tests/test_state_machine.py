import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.factory import AgentFactory
from app.execution.manager import ExecutionManager
from app.shared.enums.project_state import ProjectState
from app.shared.models.stage_artifact import StageArtifact
from app.workflow.engine import WorkflowEngine
from app.workflow.manager import WorkflowManager
from app.workspace.manager import WorkspaceManager


class _StubSuccessAgent:
    def execute(self, context: object) -> StageArtifact:
        return StageArtifact(
            artifact_id="",
            name="stub-output",
            content="stub content for stage",
            status="Generated",
        )


class _StubLearningLoop:
    def get_relevant_patterns(self, task: str, stage: str, project_id: str = "", top_k: int = 3) -> list[str]:
        return []

    def record_trajectory(self, trajectory: object) -> None:
        return None


def _build_test_rig(tmp_dir: Path):
    workspace_manager = WorkspaceManager(root=tmp_dir / "workspaces")
    factory = AgentFactory()
    stub = _StubSuccessAgent()
    for key in [
        "qa",
        "product_owner",
        "architect",
        "designer",
        "planner",
        "sprint_planner",
        "backend",
        "frontend",
        "devops",
        "strategic_review",
        "security",
        "file_planner",
        "document",
        "retro",
    ]:
        factory.registry.register(key, stub)
    execution_manager = ExecutionManager(agent_factory=factory)
    workflow_engine = WorkflowEngine(
        execution_manager=execution_manager,
        learning_loop=_StubLearningLoop(),
        workspace_manager=workspace_manager,
    )
    workflow_manager = WorkflowManager(
        engine=workflow_engine,
        workspace_manager=workspace_manager,
    )
    return workflow_manager, workspace_manager


class StateMachineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.workflow_manager, self.workspace_manager = _build_test_rig(self.tmp_dir)
        self.project_id = "test-project-123"
        self.workspace_manager.create_workspace(self.project_id, "Test App", "Description")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_state_transitions_in_order(self) -> None:
        initial_state = self.workspace_manager.get_state(self.project_id)
        self.assertEqual(initial_state, ProjectState.EMPTY)

        result = self.workflow_manager.run(self.project_id, "Build app")
        self.assertEqual(result.state, ProjectState.DESIGN_REVIEW_PENDING)
        self.assertTrue(result.requires_user_action)
        self.assertEqual(result.action_needed, "review_design")

    def test_crash_recovery_resumes_from_last_state(self) -> None:
        self.workspace_manager.update_state(self.project_id, ProjectState.ARCHITECTURE_READY)

        result = self.workflow_manager.run(self.project_id, "Build app")
        self.assertEqual(result.state, ProjectState.DESIGN_REVIEW_PENDING)

    def test_design_review_pauses_pipeline(self) -> None:
        self.workspace_manager.update_state(self.project_id, ProjectState.DESIGN_REVIEW_PENDING)
        result = self.workflow_manager.run(self.project_id, "Build app")
        self.assertEqual(result.state, ProjectState.DESIGN_REVIEW_PENDING)
        self.assertTrue(result.requires_user_action)

    def test_design_approval_advances_to_sprint_planning(self) -> None:
        self.workspace_manager.update_state(self.project_id, ProjectState.DESIGN_REVIEW_PENDING)
        self.workspace_manager.update_design_review(self.project_id, "approved", "Looks great")
        self.workspace_manager.update_state(self.project_id, ProjectState.DESIGN_APPROVED)

        result = self.workflow_manager.run(self.project_id, "Build app")
        self.assertIn(
            result.state,
            [
                ProjectState.DEPLOYABLE,
                ProjectState.ALL_SPRINTS_COMPLETE,
                ProjectState.QA_COMPLETE,
                ProjectState.SPRINT_IN_PROGRESS,
            ],
        )
        self.assertTrue(result.success)

    def test_pipeline_result_has_correct_state(self) -> None:
        result = self.workflow_manager.run(self.project_id, "Build app")
        self.assertIsInstance(result.state, ProjectState)
        self.assertEqual(result.state, ProjectState.DESIGN_REVIEW_PENDING)


if __name__ == "__main__":
    unittest.main()
