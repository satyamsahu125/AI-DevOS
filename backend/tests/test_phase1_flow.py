import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.artifact.manager import ArtifactManager
from app.review.manager import ReviewManager
from app.shared.enums.stage import Stage
from app.workspace.manager import WorkspaceManager


class Phase1FlowTests(unittest.TestCase):
    def test_workspace_layout_is_created(self) -> None:
        workspace_dir = Path(__file__).resolve().parents[1] / "temp-workspace"
        manager = WorkspaceManager(workspace_dir)
        workspace = manager.create_workspace("demo")
        self.assertTrue(workspace.exists())
        self.assertTrue((workspace / "docs").exists())
        self.assertTrue((workspace / "artifacts").exists())

    def test_artifact_and_review_flow(self) -> None:
        workspace_manager = WorkspaceManager(Path(__file__).resolve().parents[1] / "temp-workspace")
        manager = ArtifactManager(storage_dir=Path(__file__).resolve().parents[1] / "artifacts-test", workspace_manager=workspace_manager)
        saved = manager.save_artifact("phase1-flow-test", Stage.ProductOwner, "Collect user requirements")
        self.assertEqual(saved.status, "Stored")
        review = ReviewManager().review(saved)
        self.assertTrue(review.approved)


if __name__ == "__main__":
    unittest.main()
