"""test_intelligence_layer_wiring.py — Phase 3 Task 1: intelligence layer wired after sprint.

Verifies:
  1. FileIndexer.index_project() indexes .py/.ts/.js/etc. files under a workspace dir.
  2. FileIndexer.index_project() skips blacklisted dirs (node_modules, __pycache__, etc.).
  3. FileIndexer.index_project() returns 0 gracefully when workspace doesn't exist.
  4. PipelineSupervisor._trigger_intelligence_index() calls all three components.
  5. _trigger_intelligence_index() is non-blocking — component errors don't raise.
  6. _trigger_intelligence_index() skips dep_graph/summarizer when they are None.
  7. PipelineSupervisor._run_sprints() calls _trigger_intelligence_index after success.
  8. WorkflowManager passes dependency_graph and code_summarizer to PipelineSupervisor.

Running:
    cd backend
    python -m pytest tests/test_intelligence_layer_wiring.py -v
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from app.intelligence.file_indexer import FileIndexer
from app.workflow.pipeline_supervisor import PipelineSupervisor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_supervisor(
    file_indexer=None,
    dependency_graph=None,
    code_summarizer=None,
) -> PipelineSupervisor:
    """Build a PipelineSupervisor with minimal mocked deps."""
    workspace = MagicMock()
    workspace.get_workspace_path.return_value = Path("/tmp/fake_workspace")
    workspace.get_state.return_value = MagicMock()
    workspace.get_sprint_plan.return_value = None
    workspace.update_state = MagicMock()

    engine = MagicMock()
    sprint_executor = MagicMock()
    settings = MagicMock()

    return PipelineSupervisor(
        workspace=workspace,
        engine=engine,
        sprint_executor=sprint_executor,
        settings=settings,
        file_indexer=file_indexer,
        dependency_graph=dependency_graph,
        code_summarizer=code_summarizer,
    )


# ---------------------------------------------------------------------------
# 1-3: FileIndexer.index_project()
# ---------------------------------------------------------------------------

class TestFileIndexerIndexProject:

    def _make_indexer(self) -> FileIndexer:
        """FileIndexer backed by an in-memory SQLite database."""
        return FileIndexer(db_path=":memory:")

    def test_indexes_py_and_ts_files(self):
        """index_project() should index .py, .ts, and .js files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "main.py").write_text("def hello(): pass\n")
            Path(tmpdir, "app.ts").write_text("export const x = 1;\n")
            Path(tmpdir, "utils.js").write_text("function add(a,b){return a+b;}\n")

            indexer = self._make_indexer()
            count = indexer.index_project("proj-1", tmpdir, sprint_number=1)

            assert count == 3
            indexed = indexer.get_project_index("proj-1")
            paths = {f.file_path for f in indexed}
            assert "main.py" in paths
            assert "app.ts" in paths
            assert "utils.js" in paths

    def test_skips_node_modules(self):
        """index_project() must not index files inside node_modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "main.py").write_text("x = 1\n")
            nm = Path(tmpdir, "node_modules")
            nm.mkdir()
            Path(nm, "lodash.js").write_text("module.exports = {}\n")

            indexer = self._make_indexer()
            count = indexer.index_project("proj-2", tmpdir)

            assert count == 1
            paths = {f.file_path for f in indexer.get_project_index("proj-2")}
            assert not any("node_modules" in p for p in paths)

    def test_skips_pycache(self):
        """index_project() must not index files inside __pycache__."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "app.py").write_text("pass\n")
            cache = Path(tmpdir, "__pycache__")
            cache.mkdir()
            Path(cache, "app.cpython-310.pyc").write_bytes(b"\x00" * 16)

            indexer = self._make_indexer()
            count = indexer.index_project("proj-3", tmpdir)

            # Only app.py indexed; .pyc is also filtered by extension
            assert count == 1

    def test_returns_zero_for_missing_workspace(self):
        """index_project() must return 0 and not raise when path doesn't exist."""
        indexer = self._make_indexer()
        count = indexer.index_project("proj-4", "/nonexistent/path/xyz")
        assert count == 0

    def test_skips_non_source_extensions(self):
        """index_project() skips binary and non-source files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "image.png").write_bytes(b"\x89PNG\r\n")
            Path(tmpdir, "data.csv").write_text("a,b\n1,2\n")
            Path(tmpdir, "code.py").write_text("print('hi')\n")

            indexer = self._make_indexer()
            count = indexer.index_project("proj-5", tmpdir)

            assert count == 1  # only .py

    def test_sprint_number_stored(self):
        """index_project() should pass sprint_number through to index_file()."""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "module.py").write_text("class A: pass\n")

            indexer = self._make_indexer()
            indexer.index_project("proj-6", tmpdir, sprint_number=3)

            indexed = indexer.get_project_index("proj-6")
            assert indexed[0].sprint_number == 3


# ---------------------------------------------------------------------------
# 4-6: PipelineSupervisor._trigger_intelligence_index()
# ---------------------------------------------------------------------------

class TestTriggerIntelligenceIndex:

    def test_calls_all_three_components(self):
        """When all three are wired, _trigger_intelligence_index calls all three."""
        fi = MagicMock()
        fi.index_project.return_value = 5
        dg = MagicMock()
        cs = MagicMock()

        sup = _make_supervisor(file_indexer=fi, dependency_graph=dg, code_summarizer=cs)
        sup._trigger_intelligence_index("proj-a", sprint_number=2)

        workspace_path = sup.workspace.get_workspace_path.return_value
        fi.index_project.assert_called_once_with("proj-a", str(workspace_path), 2)
        dg.build.assert_called_once_with("proj-a")
        cs.build_project_overview.assert_called_once_with("proj-a")

    def test_non_blocking_on_file_indexer_error(self):
        """If file_indexer.index_project raises, no exception propagates."""
        fi = MagicMock()
        fi.index_project.side_effect = RuntimeError("disk full")
        dg = MagicMock()
        cs = MagicMock()

        sup = _make_supervisor(file_indexer=fi, dependency_graph=dg, code_summarizer=cs)
        # Must not raise
        sup._trigger_intelligence_index("proj-b")

    def test_non_blocking_on_dep_graph_error(self):
        """If dependency_graph.build raises, no exception propagates."""
        fi = MagicMock()
        fi.index_project.return_value = 3
        dg = MagicMock()
        dg.build.side_effect = ValueError("bad graph")
        cs = MagicMock()

        sup = _make_supervisor(file_indexer=fi, dependency_graph=dg, code_summarizer=cs)
        sup._trigger_intelligence_index("proj-c")
        # Should still have called file_indexer
        fi.index_project.assert_called_once()

    def test_skips_dep_graph_when_none(self):
        """When dependency_graph is None, build() is not called."""
        fi = MagicMock()
        fi.index_project.return_value = 1
        cs = MagicMock()

        sup = _make_supervisor(file_indexer=fi, dependency_graph=None, code_summarizer=cs)
        sup._trigger_intelligence_index("proj-d")

        fi.index_project.assert_called_once()
        cs.build_project_overview.assert_called_once()

    def test_skips_summarizer_when_none(self):
        """When code_summarizer is None, build_project_overview() is not called."""
        fi = MagicMock()
        fi.index_project.return_value = 1
        dg = MagicMock()

        sup = _make_supervisor(file_indexer=fi, dependency_graph=dg, code_summarizer=None)
        sup._trigger_intelligence_index("proj-e")

        fi.index_project.assert_called_once()
        dg.build.assert_called_once()

    def test_no_call_when_file_indexer_none(self):
        """When file_indexer is None, nothing is called and no error occurs."""
        dg = MagicMock()
        cs = MagicMock()

        sup = _make_supervisor(file_indexer=None, dependency_graph=dg, code_summarizer=cs)
        sup._trigger_intelligence_index("proj-f")

        dg.build.assert_not_called()
        cs.build_project_overview.assert_not_called()


# ---------------------------------------------------------------------------
# 7: _run_sprints() calls _trigger_intelligence_index after success
# ---------------------------------------------------------------------------

class TestRunSprintsCallsIntelligenceTrigger:

    def test_trigger_called_after_successful_sprint(self):
        """_run_sprints must call _trigger_intelligence_index after each successful sprint."""
        fi = MagicMock()
        fi.index_project.return_value = 2

        sup = _make_supervisor(file_indexer=fi)

        # Build a minimal sprint plan
        sprint = MagicMock()
        sprint.sprint_number = 1

        sprint_plan = MagicMock()
        sprint_plan.sprints = [sprint]
        sprint_plan.stale = False

        sup.workspace.get_sprint_plan.return_value = sprint_plan
        sup.workspace.load_project_json.return_value = {"completed_sprints": [], "stages_completed": []}
        sup.workspace.get_state.return_value = MagicMock()

        # Sprint succeeds
        sprint_result = MagicMock()
        sprint_result.success = True
        sup._sprint_executor.run.return_value = sprint_result

        # Patch _pin_dependencies, _run_sandbox, _commit_sprint_to_git, _start_preview
        # so we don't need their deps wired
        with (
            patch.object(sup, "_pin_dependencies"),
            patch.object(sup, "_run_sandbox"),
            patch.object(sup, "_commit_sprint_to_git"),
            patch.object(sup, "_start_preview"),
        ):
            sup._run_sprints("proj-g", "request")

        fi.index_project.assert_called_once()


# ---------------------------------------------------------------------------
# 8: WorkflowManager passes dependency_graph and code_summarizer
# ---------------------------------------------------------------------------

class TestWorkflowManagerPassesDeps:

    def test_dependency_graph_forwarded_to_pipeline_supervisor(self):
        """WorkflowManager must forward dependency_graph to PipelineSupervisor."""
        from app.workflow.manager import WorkflowManager

        fake_dg = MagicMock()
        fake_cs = MagicMock()
        captured: dict = {}

        def fake_ps(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        engine = MagicMock()
        engine.workspace_manager = MagicMock()
        engine.artifact_manager = MagicMock()
        engine.broadcaster = MagicMock()
        engine.memory_manager = None

        # SprintExecutor, AgentFactory, ConfigurationManager, ChangeManager, and
        # ImpactAnalyzer are local imports inside WorkflowManager.__init__; patch
        # at their source module paths.
        with (
            patch("app.workflow.manager.PipelineSupervisor", side_effect=fake_ps),
            patch("app.workflow.sprint_executor.SprintExecutor"),
            patch("app.agents.factory.AgentFactory"),
            patch("app.config.manager.ConfigurationManager"),
            patch("app.workflow.change_manager.ChangeManager"),
            patch("app.workflow.impact_analyzer.ImpactAnalyzer"),
        ):
            WorkflowManager(
                engine=engine,
                workspace_manager=MagicMock(),
                dependency_graph=fake_dg,
                code_summarizer=fake_cs,
            )

        assert captured.get("dependency_graph") is fake_dg
        assert captured.get("code_summarizer") is fake_cs
