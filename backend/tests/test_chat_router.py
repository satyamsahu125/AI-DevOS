"""Unit tests for ChatRouter agent and chat endpoints (BUG-003)."""

import unittest
from unittest.mock import MagicMock

from app.agents.chat_router import ChatResponse, ChatRouter


class ChatRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_llm = MagicMock()
        self.mock_artifacts = MagicMock()
        self.mock_workflow = MagicMock()
        self.mock_workspace = MagicMock()

        self.mock_llm.generate_text.return_value = "The architect selected SQLite and FastAPI."

        self.router = ChatRouter(
            llm_manager=self.mock_llm,
            artifact_manager=self.mock_artifacts,
            workflow_manager=self.mock_workflow,
            workspace_manager=self.mock_workspace,
        )

    def test_detects_status_intent(self) -> None:
        self.mock_workspace.load_project_json.return_value = {
            "state": "sprint_in_progress",
            "current_stage": "BackendDeveloper",
            "stages_completed": ["strategic_review", "product_owner", "architect"],
        }

        res = self.router.handle("proj-1", "What's the project status?")
        self.assertIsInstance(res, ChatResponse)
        self.assertIn("Project status:", res.reply)
        self.assertIn("sprint_in_progress", res.reply)

    def test_detects_read_artifact_intent(self) -> None:
        mock_artifact = MagicMock()
        mock_artifact.content = "Architecture decision: Use PostgreSQL database."
        self.mock_artifacts.get_artifact.return_value = mock_artifact

        res = self.router.handle("proj-1", "What did the architect decide?")
        self.assertIsInstance(res, ChatResponse)
        self.assertEqual(res.artifacts_read, ["architect"])
        self.assertIn("SQLite and FastAPI", res.reply)

    def test_detects_trigger_stage_intent(self) -> None:
        self.mock_workflow.run_stage.return_value = MagicMock(success=True)

        res = self.router.handle("proj-1", "Re-run the QA stage")
        self.assertIsInstance(res, ChatResponse)
        self.assertEqual(res.stage_triggered, "qa")
        self.assertIn("re-run the qa stage", res.reply.lower())


if __name__ == "__main__":
    unittest.main()
