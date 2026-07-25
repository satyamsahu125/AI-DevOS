import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.workflow import DesignApprovalRequest, get_design_review, post_design_review
from app.artifact.manager import ArtifactManager
from app.shared.enums.project_state import ProjectState
from app.shared.enums.stage import Stage
from app.shared.schemas.design_schema import ColorPalette, ComponentSpec, DesignArtifact, PageSpec, TypographySpec
from app.workspace.manager import WorkspaceManager


class DesignReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_design_review_"))
        self.workspace_manager = WorkspaceManager(root=self.tmp_dir)
        self.artifact_manager = ArtifactManager(workspace_manager=self.workspace_manager)

    def test_design_artifact_has_required_fields(self) -> None:
        artifact = DesignArtifact(
            project_id="proj-design-1",
            project_name="Test App",
            color_palette=ColorPalette(primary="#3B82F6", secondary="#10B981"),
            typography=TypographySpec(heading_font="Inter", body_font="Inter"),
            pages=[PageSpec(page_id="p1", name="LoginPage", route="/login", layout="centered", components=["c1"])],
            components=[ComponentSpec(component_id="c1", name="LoginForm", shadcn_component="Card", tailwind_classes="w-full max-w-md")],
        )
        self.assertEqual(artifact.color_palette.primary, "#3B82F6")
        self.assertEqual(artifact.pages[0].name, "LoginPage")
        self.assertEqual(artifact.components[0].shadcn_component, "Card")

    def test_design_review_pauses_pipeline(self) -> None:
        proj_id = "proj-pause-1"
        self.workspace_manager.create_workspace(proj_id)
        self.workspace_manager.update_state(proj_id, ProjectState.DESIGN_REVIEW_PENDING)
        res = get_design_review(proj_id, workspace_manager=self.workspace_manager, artifact_manager=self.artifact_manager)
        self.assertEqual(res["project_id"], proj_id)
        self.assertEqual(res["state"], "design_review_pending")
        self.assertIn("design", res)

    def test_rejection_stores_feedback(self) -> None:
        proj_id = "proj-reject-1"
        self.workspace_manager.create_workspace(proj_id)
        self.workspace_manager.update_state(proj_id, ProjectState.DESIGN_REVIEW_PENDING)

        req = DesignApprovalRequest(approved=False, feedback="Change theme to dark mode and add sidebar navigation.")
        res = post_design_review(proj_id, req, workspace_manager=self.workspace_manager)

        self.assertEqual(res["state"], "design_revision")
        self.assertEqual(res["iteration"], 2)

        data = self.workspace_manager.load_project_json(proj_id)
        self.assertEqual(data["design_review"]["status"], "revision_requested")
        self.assertIn("dark mode", data["design_review"]["user_feedback"])
        self.assertEqual(self.workspace_manager.get_state(proj_id), ProjectState.DESIGN_READY)

    def test_revision_includes_previous_feedback(self) -> None:
        proj_id = "proj-rev-1"
        self.workspace_manager.create_workspace(proj_id)
        dr_data = {"status": "revision_requested", "user_feedback": "Use dark theme", "iteration": 2}
        self.workspace_manager.update_project_json(proj_id, {"design_review": dr_data})
        data = self.workspace_manager.load_project_json(proj_id)
        self.assertEqual(data["design_review"]["user_feedback"], "Use dark theme")
        self.assertEqual(data["design_review"]["iteration"], 2)

    def test_approval_advances_to_sprint_planning(self) -> None:
        proj_id = "proj-approve-1"
        self.workspace_manager.create_workspace(proj_id)
        self.workspace_manager.update_state(proj_id, ProjectState.DESIGN_REVIEW_PENDING)

        req = DesignApprovalRequest(approved=True, feedback="Looks great!")
        res = post_design_review(proj_id, req, workspace_manager=self.workspace_manager)

        self.assertEqual(res["state"], "design_approved")
        self.assertEqual(self.workspace_manager.get_state(proj_id), ProjectState.DESIGN_APPROVED)

    def test_approval_with_modified_design(self) -> None:
        proj_id = "proj-mod-1"
        self.workspace_manager.create_workspace(proj_id)
        self.workspace_manager.update_state(proj_id, ProjectState.DESIGN_REVIEW_PENDING)

        modified_design = {
            "project_id": proj_id,
            "components": [{"component_id": "component_0", "name": "HeroSection", "shadcn_component": "Hero"}],
            "user_modified": True,
        }
        req = DesignApprovalRequest(approved=True, feedback="Approved with custom Puck changes", modified_design=modified_design)
        res = post_design_review(proj_id, req, workspace_manager=self.workspace_manager, artifact_manager=self.artifact_manager)

        self.assertEqual(res["state"], "design_approved")
        loaded = self.workspace_manager.load_approved_design(proj_id)
        self.assertIsNotNone(loaded)
        self.assertTrue(loaded.get("user_modified"))
        self.assertEqual(loaded["components"][0]["name"], "HeroSection")


if __name__ == "__main__":
    unittest.main()
