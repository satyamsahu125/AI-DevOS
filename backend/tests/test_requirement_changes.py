from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.workflow import (
    ChangeConfirmRequest,
    RequirementChangeRequest,
    confirm_requirement_change,
    submit_requirement_change,
)
from app.artifact.manager import ArtifactManager
from app.workflow.impact_analyzer import ImpactAnalyzer
from app.workflow.manager import WorkflowManager
from app.workspace.manager import WorkspaceManager


class TestRequirementChanges(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_req_changes_"))
        self.workspace_manager = WorkspaceManager(root=self.tmp_dir)
        self.artifact_manager = ArtifactManager(workspace_manager=self.workspace_manager)
        self.mock_llm = MagicMock()
        self.mock_llm.generate_text.return_value = "add_feature"
        self.impact_analyzer = ImpactAnalyzer(
            llm_manager=self.mock_llm,
            artifact_manager=self.artifact_manager,
        )
        self.workflow_manager = WorkflowManager(
            workspace_manager=self.workspace_manager,
            impact_analyzer=self.impact_analyzer,
        )

    def test_impact_analyzer_add_feature_affects_backend(self) -> None:
        analysis = self.impact_analyzer.analyze(
            "proj-1",
            "Add shopping cart feature",
            ["strategic_review", "product_owner", "architect"],
        )
        self.assertIn("backend", analysis.affected_stages)
        self.assertIn("qa", analysis.affected_stages)
        self.assertIn("strategic_review", analysis.safe_stages)

    def test_impact_analyzer_modify_ui_spares_backend(self) -> None:
        self.mock_llm.generate_text.return_value = "modify_ui"
        completed_stages = [
            "strategic_review",
            "product_owner",
            "architect",
            "designer",
            "security",
            "sprint_planner",
            "scrum_master",
            "file_planner",
            "backend",
            "frontend",
            "qa",
        ]
        analysis = self.impact_analyzer.analyze(
            "proj-1",
            "Change the button color to blue",
            completed_stages,
        )
        self.assertIn("designer", analysis.affected_stages)
        self.assertIn("frontend", analysis.affected_stages)
        self.assertNotIn("backend", analysis.affected_stages)

    def test_apply_change_removes_affected_stages(self) -> None:
        proj_id = "test-apply-change"
        self.workspace_manager.create_workspace(proj_id)
        all_completed = [
            "strategic_review",
            "product_owner",
            "architect",
            "designer",
            "security",
            "sprint_planner",
            "scrum_master",
            "file_planner",
            "backend",
            "frontend",
            "qa",
        ]
        self.workspace_manager.update_project_json(
            proj_id,
            {
                "stages_completed": all_completed,
                "pending_change": {
                    "change_id": "change-uuid-1",
                    "description": "UI modification",
                    "affected_stages": ["designer", "frontend", "qa"],
                    "safe_stages": [
                        "strategic_review",
                        "product_owner",
                        "architect",
                        "security",
                        "sprint_planner",
                        "scrum_master",
                        "file_planner",
                        "backend",
                    ],
                    "analyzed_at": "2026-07-26T00:00:00Z",
                },
            },
        )

        result = self.workflow_manager.apply_requirement_change(
            project_id=proj_id,
            change_id="change-uuid-1",
            confirmed=True,
            user_comment="Make sidebar collapsible",
        )
        self.assertEqual(result["status"], "applied")
        self.assertIn("designer", result["stages_removed"])
        self.assertIn("frontend", result["stages_removed"])
        self.assertIn("strategic_review", result["stages_kept"])

        pj = self.workspace_manager.load_project_json(proj_id)
        self.assertNotIn("designer", pj["stages_completed"])
        self.assertNotIn("frontend", pj["stages_completed"])
        self.assertIn("strategic_review", pj["stages_completed"])

    def test_cancel_change_restores_state(self) -> None:
        proj_id = "test-cancel-change"
        self.workspace_manager.create_workspace(proj_id)
        stages = ["strategic_review", "product_owner", "architect"]
        self.workspace_manager.update_project_json(
            proj_id,
            {
                "stages_completed": stages,
                "pending_change": {
                    "change_id": "change-uuid-cancel",
                    "description": "Test cancel",
                    "affected_stages": ["architect"],
                    "safe_stages": ["strategic_review", "product_owner"],
                    "analyzed_at": "2026-07-26T00:00:00Z",
                },
            },
        )

        result = self.workflow_manager.apply_requirement_change(
            project_id=proj_id,
            change_id="change-uuid-cancel",
            confirmed=False,
        )
        self.assertEqual(result["status"], "cancelled")

        pj = self.workspace_manager.load_project_json(proj_id)
        self.assertEqual(pj["stages_completed"], stages)
        self.assertIsNone(pj.get("pending_change"))

    def test_change_endpoint_returns_impact_analysis(self) -> None:
        proj_id = "test-endpoint-proj"
        self.workspace_manager.create_workspace(proj_id)
        res = submit_requirement_change(
            project_id=proj_id,
            req=RequirementChangeRequest(description="Add notifications"),
            workspace_manager=self.workspace_manager,
            manager=self.workflow_manager,
        )
        self.assertIn("affected_stages", res)
        self.assertIn("safe_stages", res)
        self.assertIn("explanation", res)
        self.assertIn("change_id", res)

    def test_confirm_endpoint_applies_change(self) -> None:
        proj_id = "test-confirm-endpoint"
        self.workspace_manager.create_workspace(proj_id)
        analysis = self.workflow_manager.submit_requirement_change(
            proj_id, "Add dark mode"
        )
        res = confirm_requirement_change(
            project_id=proj_id,
            req=ChangeConfirmRequest(
                change_id=analysis.change_id,
                confirmed=True,
                comment="Also dark mode toggle button",
            ),
            workspace_manager=self.workspace_manager,
            manager=self.workflow_manager,
        )
        self.assertEqual(res["status"], "applied")


def test_impact_analyzer_add_feature_affects_backend():
    mock_llm = MagicMock()
    mock_llm.generate_text.return_value = "add_feature"
    mock_artifacts = MagicMock()
    analyzer = ImpactAnalyzer(mock_llm, mock_artifacts)
    analysis = analyzer.analyze(
        "proj-1",
        "Add shopping cart feature",
        ["strategic_review", "product_owner", "architect"],
    )
    assert "backend" in analysis.affected_stages
    assert "qa" in analysis.affected_stages
    assert "strategic_review" in analysis.safe_stages


def test_impact_analyzer_modify_ui_spares_backend():
    mock_llm = MagicMock()
    mock_llm.generate_text.return_value = "modify_ui"
    mock_artifacts = MagicMock()
    analyzer = ImpactAnalyzer(mock_llm, mock_artifacts)
    completed_stages = [
        "strategic_review",
        "product_owner",
        "architect",
        "designer",
        "security",
        "sprint_planner",
        "scrum_master",
        "file_planner",
        "backend",
        "frontend",
        "qa",
    ]
    analysis = analyzer.analyze(
        "proj-1",
        "Change the button color to blue",
        completed_stages,
    )
    assert "designer" in analysis.affected_stages
    assert "frontend" in analysis.affected_stages
    assert "backend" not in analysis.affected_stages


def test_apply_change_removes_affected_stages():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_apply_func_"))
    ws = WorkspaceManager(root=tmp_dir)
    wm = WorkflowManager(workspace_manager=ws)
    proj_id = "test-apply-func"
    ws.create_workspace(proj_id)
    ws.update_project_json(
        proj_id,
        {
            "stages_completed": [
                "strategic_review",
                "product_owner",
                "architect",
                "designer",
                "frontend",
            ],
            "pending_change": {
                "change_id": "c-123",
                "description": "Modify UI",
                "affected_stages": ["designer", "frontend"],
                "safe_stages": ["strategic_review", "product_owner", "architect"],
            },
        },
    )

    result = wm.apply_requirement_change(
        project_id=proj_id,
        change_id="c-123",
        confirmed=True,
    )
    assert "designer" in result["stages_removed"]
    assert "frontend" in result["stages_removed"]
    assert "strategic_review" in result["stages_kept"]


def test_cancel_change_restores_state():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_cancel_func_"))
    ws = WorkspaceManager(root=tmp_dir)
    wm = WorkflowManager(workspace_manager=ws)
    proj_id = "test-cancel-func"
    ws.create_workspace(proj_id)
    ws.update_project_json(
        proj_id,
        {
            "stages_completed": ["strategic_review"],
            "pending_change": {
                "change_id": "c-456",
                "description": "Modify API",
                "affected_stages": ["architect"],
                "safe_stages": ["strategic_review"],
            },
        },
    )
    result = wm.apply_requirement_change(
        project_id=proj_id,
        change_id="c-456",
        confirmed=False,
    )
    assert result["status"] == "cancelled"


def test_change_endpoint_returns_impact_analysis():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_ep_func_"))
    ws = WorkspaceManager(root=tmp_dir)
    mock_llm = MagicMock()
    mock_llm.generate_text.return_value = "add_feature"
    ia = ImpactAnalyzer(mock_llm, MagicMock())
    wm = WorkflowManager(workspace_manager=ws, impact_analyzer=ia)

    proj_id = "ep-test"
    ws.create_workspace(proj_id)
    res = submit_requirement_change(
        project_id=proj_id,
        req=RequirementChangeRequest(description="Add notifications"),
        workspace_manager=ws,
        manager=wm,
    )
    assert "affected_stages" in res
    assert "safe_stages" in res
    assert "explanation" in res
    assert "change_id" in res


def test_confirm_endpoint_applies_change():
    tmp_dir = Path(tempfile.mkdtemp(prefix="test_conf_func_"))
    ws = WorkspaceManager(root=tmp_dir)
    mock_llm = MagicMock()
    mock_llm.generate_text.return_value = "add_feature"
    ia = ImpactAnalyzer(mock_llm, MagicMock())
    wm = WorkflowManager(workspace_manager=ws, impact_analyzer=ia)

    proj_id = "conf-test"
    ws.create_workspace(proj_id)
    analysis = wm.submit_requirement_change(proj_id, "Add dark mode")
    res = confirm_requirement_change(
        project_id=proj_id,
        req=ChangeConfirmRequest(change_id=analysis.change_id, confirmed=True, comment=""),
        workspace_manager=ws,
        manager=wm,
    )
    assert res["status"] == "applied"
