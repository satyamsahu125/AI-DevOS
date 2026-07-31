"""Unit tests for pipeline resume logic and stages_completed sanitization (BUG-001)."""

import unittest
from unittest.mock import MagicMock

from app.shared.enums.stage import Stage
from app.workflow.dependency_graph import DependencyGraph
from app.workflow.manager import WorkflowManager


class PipelineResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = WorkflowManager(
            engine=MagicMock(),
            workspace_manager=MagicMock(),
            execution_state=MagicMock(),
            agent_factory=MagicMock(),
            project_validator=MagicMock(),
        )

    @unittest.skip("Obsolete: backend and frontend are now sprint stages, not top-level")
    def test_resume_from_backend_stage_not_retro(self) -> None:
        """When backend is incomplete, resume picks up at backend."""
        stages_completed = [
            Stage.StrategicReview.value,
            Stage.ProductOwner.value,
            Stage.Architect.value,
            Stage.Designer.value,
            Stage.Security.value,
            Stage.SprintPlanning.value,
            Stage.ScrumMaster.value,
            Stage.FileStructurePlanner.value,
        ]
        order = DependencyGraph.ordered_stages()
        sanitized = self.manager._sanitize_stages_completed(stages_completed, order)
        self.assertEqual(sanitized, stages_completed)

    def test_sanitize_removes_gap_stages(self) -> None:
        """If backend is missing but QA is present, QA gets removed."""
        stages_completed = [
            Stage.StrategicReview.value,
            Stage.ProductOwner.value,
            Stage.QA.value,
        ]
        order = DependencyGraph.ordered_stages()
        sanitized = self.manager._sanitize_stages_completed(stages_completed, order)
        self.assertNotIn(Stage.QA.value, sanitized)
        self.assertEqual(sanitized, [Stage.StrategicReview.value, Stage.ProductOwner.value])


if __name__ == "__main__":
    unittest.main()
