"""Tests for all fixes applied from the code-review report.

Each test corresponds directly to a numbered fix:
  FIX-001  ArtifactManager missing import in dependencies.py
  FIX-002  CHANGE_REQUESTED state missing from WorkflowManager.run() loop
  FIX-002b else safety catch for all unhandled states
  FIX-003  DI bypass in _run_sprint (container wiring)
  FIX-004  LessonStore.get_lessons() never called before stage runs
  FIX-005  Double validation in _run_validation_with_healing
  FIX-006  DependencyGraph.has_dependency() hardcoded to "product_owner"
  FIX-007  `Any` not imported in engine.py / container.py
  FIX-008  Empty project_id guard missing in WorkflowManager.run()
  FIX-009  ScrumMaster artifact not injected into sprint context
  FIX-010  FileStructurePlanner ran twice (global + per-sprint)
  FIX-011  No sprint-level retry
  FIX-012/013  WorkflowTransition / WorkflowDependency dead code removed
"""

from __future__ import annotations

import ast
import pathlib
import sys
import unittest
from unittest.mock import MagicMock, patch, call

# Add backend/ to sys.path so `app.*` imports resolve — matches all other test
# files in this suite (e.g. test_sprint_planner.py line 6).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# Patch SQLite-backed singletons that try to write to the Windows mount
# before any app import happens. Must come after sys.path is set.
sys.modules.setdefault("app.execution.safety_policy", MagicMock())

BASE = pathlib.Path(__file__).parent.parent  # backend/


class Fix001ArtifactManagerImport(unittest.TestCase):
    """FIX-001: ArtifactManager must be imported in api/dependencies.py."""

    def test_artifact_manager_in_imports(self):
        src = (BASE / "app/api/dependencies.py").read_text()
        tree = ast.parse(src)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }
        self.assertIn(
            "ArtifactManager",
            imported,
            "ArtifactManager must be explicitly imported in dependencies.py so the "
            "get_artifact_manager() return annotation resolves at runtime.",
        )


class Fix002ChangeRequestedState(unittest.TestCase):
    """FIX-002: WorkflowManager.run() must handle CHANGE_REQUESTED and have an else catch."""

    def _make_wm(self, state):
        from app.shared.enums.project_state import ProjectState
        from app.workflow.manager import WorkflowManager

        engine = MagicMock()
        ws = MagicMock()
        ws.get_state.return_value = state
        ws.load_project_json.return_value = {
            "pending_change": {"description": "Add OAuth"},
            "stages_completed": [],
        }
        es = MagicMock()
        es.is_running.return_value = False
        return WorkflowManager(engine=engine, workspace_manager=ws, execution_state=es)

    def test_change_requested_returns_user_action(self):
        from app.shared.enums.project_state import ProjectState

        wm = self._make_wm(ProjectState.CHANGE_REQUESTED)
        result = wm.run("proj-001", "build")
        self.assertEqual(result.state, ProjectState.CHANGE_REQUESTED)
        self.assertTrue(result.requires_user_action)
        self.assertEqual(result.action_needed, "confirm_change")
        self.assertIn("pending", result.message.lower())

    def test_unhandled_state_returns_failure_not_infinite_loop(self):
        from app.shared.enums.project_state import ProjectState

        for unhandled in (ProjectState.IMPACT_ANALYZED, ProjectState.REPLANNING):
            with self.subTest(state=unhandled):
                wm = self._make_wm(unhandled)
                result = wm.run("proj-002", "build")
                self.assertFalse(result.success)
                self.assertIn("Unhandled pipeline state", result.message)


class Fix003ContainerWiring(unittest.TestCase):
    """FIX-003: _run_sprint() must resolve developer agents from the DI container."""

    def test_container_stored_on_init(self):
        from app.workflow.manager import WorkflowManager

        fake_container = MagicMock()
        wm = WorkflowManager(container=fake_container)
        self.assertIs(wm._container, fake_container)

    def test_none_container_falls_back_to_factory(self):
        from app.workflow.manager import WorkflowManager

        wm = WorkflowManager(container=None)
        self.assertIsNone(wm._container)

    def test_run_sprint_resolves_from_container(self):
        from types import SimpleNamespace
        from app.workflow.manager import WorkflowManager
        from app.shared.models.sprint import Sprint, SprintStatus, SprintResult

        fake_backend = MagicMock()
        fake_backend.execute_sprint.return_value = MagicMock(success=True)
        fake_frontend = MagicMock()
        fake_frontend.execute_sprint.return_value = MagicMock(success=True)

        container = MagicMock()
        container.resolve.side_effect = lambda name: {
            "backend_developer_agent": fake_backend,
            "frontend_developer_agent": fake_frontend,
        }[name]

        ws = MagicMock()
        ws.get_workspace_path.return_value = pathlib.Path("/tmp/fake_proj")
        ws.load_approved_design.return_value = None

        sprint = Sprint(
            sprint_id="s1", sprint_number=1, name="Sprint 1",
            goal="Build auth", features=["login"], status=SprintStatus.PLANNED,
        )

        wm = WorkflowManager(workspace_manager=ws, container=container)
        wm.artifact_manager = MagicMock()
        wm.artifact_manager.get_artifact.return_value = None
        wm.workspace_manager = ws
        wm.workspace = ws
        wm.project_writer = MagicMock()
        wm._run_stage = MagicMock(return_value=MagicMock(success=True, message="ok"))
        wm._load_file_plan = MagicMock(return_value=MagicMock(tech_stack={}))
        wm._load_design_artifact = MagicMock(return_value=None)

        result = wm._run_sprint("proj-003", sprint)

        container.resolve.assert_any_call("backend_developer_agent")
        container.resolve.assert_any_call("frontend_developer_agent")
        fake_backend.execute_sprint.assert_called_once()
        fake_frontend.execute_sprint.assert_called_once()


class Fix004LessonStoreWiring(unittest.TestCase):
    """FIX-004: WorkflowEngine must call lesson_store.get_lessons() before running a stage."""

    def test_with_lessons_method_exists(self):
        from app.workflow.engine import WorkflowEngine
        self.assertTrue(
            hasattr(WorkflowEngine, "_with_lessons"),
            "_with_lessons method must exist on WorkflowEngine",
        )

    def test_with_lessons_prepends_lessons(self):
        from app.workflow.engine import WorkflowEngine
        from app.memory.lesson_store import LessonStore, Lesson
        from datetime import datetime, timezone

        engine = WorkflowEngine.__new__(WorkflowEngine)
        engine.lesson_store = MagicMock()
        engine.lesson_store.get_lessons.return_value = [
            Lesson(
                lesson_id="l1", stage="ProductOwner", project_id="p1",
                what_worked="kept PRD short", what_failed="", reviewer_said="Approved",
                retry_count_when_learned=0, created_at=datetime.now(timezone.utc),
            )
        ]
        result = engine._with_lessons("Base content", "ProductOwner", "p1")
        engine.lesson_store.get_lessons.assert_called_once_with(
            stage="ProductOwner", project_id="p1", limit=3
        )
        self.assertIn("Lessons Learned", result)
        self.assertIn("kept PRD short", result)
        self.assertIn("Base content", result)

    def test_with_lessons_returns_unchanged_when_empty(self):
        from app.workflow.engine import WorkflowEngine

        engine = WorkflowEngine.__new__(WorkflowEngine)
        engine.lesson_store = MagicMock()
        engine.lesson_store.get_lessons.return_value = []
        result = engine._with_lessons("Base content", "ProductOwner", "p1")
        self.assertEqual(result, "Base content")


class Fix005NoDoubleValidation(unittest.TestCase):
    """FIX-005: _run_validation_with_healing must not call validate() before the loop."""

    def test_single_validate_call_per_attempt(self):
        from app.workflow.manager import WorkflowManager

        pv = MagicMock()
        pv.validate.return_value = MagicMock(passed=True, fixable_errors=[])

        wm = WorkflowManager.__new__(WorkflowManager)
        wm.project_validator = pv
        wm.run_stage = MagicMock()

        wm._run_validation_with_healing("proj-004", "build", max_healing_attempts=2)
        # With max_healing_attempts=2 and passing on attempt 1, validate should be called
        # exactly once (loop stops on pass) — not 3 times (pre-loop + loop).
        self.assertEqual(pv.validate.call_count, 1)


class Fix006HasDependency(unittest.TestCase):
    """FIX-006: DependencyGraph.has_dependency() must use STAGE_DEPENDENCIES."""

    def setUp(self):
        from app.workflow.dependency_graph import DependencyGraph
        self.dg = DependencyGraph()

    def test_strategic_review_has_no_dependency(self):
        self.assertFalse(self.dg.has_dependency("strategic_review"))

    def test_product_owner_has_dependency(self):
        self.assertTrue(self.dg.has_dependency("product_owner"))

    def test_backend_has_dependency(self):
        self.assertTrue(self.dg.has_dependency("backend"))

    def test_frontend_has_dependency(self):
        self.assertTrue(self.dg.has_dependency("frontend"))

    def test_unknown_stage_returns_false(self):
        self.assertFalse(self.dg.has_dependency("nonexistent_stage"))


class Fix007AnyImports(unittest.TestCase):
    """FIX-007: `from typing import Any` must be present in engine.py and container.py."""

    def test_engine_imports_any(self):
        src = (BASE / "app/workflow/engine.py").read_text()
        self.assertIn("from typing import Any", src)

    def test_container_imports_any(self):
        src = (BASE / "app/kernel/container.py").read_text()
        self.assertIn("from typing import Any", src)


class Fix008EmptyProjectIdGuard(unittest.TestCase):
    """FIX-008: WorkflowManager.run() must reject empty project_id immediately."""

    def test_empty_string_project_id(self):
        from app.workflow.manager import WorkflowManager
        from app.shared.enums.project_state import ProjectState

        wm = WorkflowManager.__new__(WorkflowManager)
        wm.execution_state = MagicMock()
        result = wm.run("", "build something")
        self.assertFalse(result.success)
        self.assertIn("project_id is required", result.message)
        self.assertEqual(result.state, ProjectState.FAILED)

    def test_none_project_id_is_also_rejected(self):
        from app.workflow.manager import WorkflowManager

        wm = WorkflowManager.__new__(WorkflowManager)
        wm.execution_state = MagicMock()
        result = wm.run(None, "build something")  # type: ignore[arg-type]
        self.assertFalse(result.success)
        self.assertIn("project_id is required", result.message)


class Fix009ScrumMasterInjection(unittest.TestCase):
    """FIX-009: _build_sprint_context() must inject ScrumMaster artifact."""

    def test_scrum_artifact_included_in_context(self):
        from app.workflow.manager import WorkflowManager
        from app.shared.models.sprint import Sprint, SprintStatus

        wm = WorkflowManager.__new__(WorkflowManager)
        scrum_artifact = MagicMock()
        scrum_artifact.content = "Daily standups at 9am. Velocity: 40 points."
        wm.artifact_manager = MagicMock()
        wm.artifact_manager.get_artifact.return_value = scrum_artifact

        sprint = Sprint(
            sprint_id="s1", sprint_number=1, name="Sprint 1",
            goal="Build auth", features=["login"], status=SprintStatus.PLANNED,
        )
        ctx = wm._build_sprint_context("proj-005", sprint, arch=None)

        self.assertIn("Daily standups", ctx)
        self.assertIn("ScrumMaster Plan", ctx)

    def test_missing_scrum_artifact_does_not_crash(self):
        from app.workflow.manager import WorkflowManager
        from app.shared.models.sprint import Sprint, SprintStatus

        wm = WorkflowManager.__new__(WorkflowManager)
        wm.artifact_manager = MagicMock()
        wm.artifact_manager.get_artifact.return_value = None

        sprint = Sprint(
            sprint_id="s1", sprint_number=1, name="Sprint 1",
            goal="Build auth", features=["login"], status=SprintStatus.PLANNED,
        )
        ctx = wm._build_sprint_context("proj-005", sprint, arch=None)
        self.assertIn("Sprint 1", ctx)  # still renders without scrum artifact


class Fix010NoDupFilePlanner(unittest.TestCase):
    """FIX-010: FileStructurePlanner must NOT appear in the DESIGN_APPROVED block."""

    def test_file_structure_planner_not_in_design_approved_block(self):
        src = (BASE / "app/workflow/manager.py").read_text()
        # Isolate the DESIGN_APPROVED block
        after_approved = src.split("ProjectState.DESIGN_APPROVED")[1]
        before_sprint_ready = after_approved.split("ProjectState.SPRINT_PLAN_READY")[0]
        self.assertNotIn(
            "FileStructurePlanner",
            before_sprint_ready,
            "FileStructurePlanner must not run globally in the DESIGN_APPROVED block; "
            "it runs per-sprint inside _run_sprint().",
        )


class Fix011SprintRetry(unittest.TestCase):
    """FIX-011: _run_next_sprint() must retry failed sprints up to 2 times."""

    def test_sprint_retried_on_failure(self):
        from app.workflow.manager import WorkflowManager
        from app.shared.models.sprint import Sprint, SprintStatus, SprintResult

        sprint = Sprint(
            sprint_id="s1", sprint_number=1, name="Sprint 1",
            goal="Build auth", features=["login"], status=SprintStatus.PLANNED,
        )

        attempt_results = [
            SprintResult(sprint_complete=False, success=False, message="LLM timeout"),
            SprintResult(sprint_complete=True, success=True, message="Sprint completed"),
        ]

        wm = WorkflowManager.__new__(WorkflowManager)
        wm._run_sprint = MagicMock(side_effect=attempt_results)

        result = wm._run_sprint_with_retry("proj-006", sprint, max_attempts=2)

        self.assertEqual(wm._run_sprint.call_count, 2)
        self.assertTrue(result.sprint_complete)

    def test_sprint_fails_after_max_attempts(self):
        from app.workflow.manager import WorkflowManager
        from app.shared.models.sprint import Sprint, SprintStatus, SprintResult

        sprint = Sprint(
            sprint_id="s1", sprint_number=1, name="Sprint 1",
            goal="Build auth", features=["login"], status=SprintStatus.PLANNED,
        )

        wm = WorkflowManager.__new__(WorkflowManager)
        wm._run_sprint = MagicMock(
            return_value=SprintResult(sprint_complete=False, success=False, message="fail")
        )

        result = wm._run_sprint_with_retry("proj-007", sprint, max_attempts=2)

        self.assertEqual(wm._run_sprint.call_count, 2)
        self.assertFalse(result.sprint_complete)


class Fix012013DeadCodeRemoved(unittest.TestCase):
    """FIX-012/013: WorkflowTransition and WorkflowDependency must be gone."""

    def test_transition_py_deleted(self):
        self.assertFalse(
            (BASE / "app/workflow/transition.py").exists(),
            "transition.py should be deleted — WorkflowTransition was a pure no-op.",
        )

    def test_dependency_py_deleted(self):
        self.assertFalse(
            (BASE / "app/workflow/dependency.py").exists(),
            "dependency.py should be deleted — WorkflowDependency.validate() always returned True.",
        )

    def test_engine_does_not_import_transition(self):
        src = (BASE / "app/workflow/engine.py").read_text()
        self.assertNotIn("WorkflowTransition", src)
        self.assertNotIn("from .transition import", src)

    def test_engine_does_not_import_dependency(self):
        src = (BASE / "app/workflow/engine.py").read_text()
        self.assertNotIn("WorkflowDependency", src)
        self.assertNotIn("from .dependency import", src)

    def test_engine_assigns_state_directly(self):
        src = (BASE / "app/workflow/engine.py").read_text()
        # After fix, engine assigns WorkflowState directly rather than via no-op wrapper
        self.assertIn("workflow.state = WorkflowState.Approved", src)
        self.assertIn("workflow.state = WorkflowState.Failed", src)


if __name__ == "__main__":
    unittest.main()
