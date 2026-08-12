"""test_context_orchestrator_get_project_state.py — Phase 3 Task 2.

Verifies:
  1. Returns all required keys even when no files are indexed (is_populated=False).
  2. Returns is_populated=True with correct data when files are indexed.
  3. files list contains file paths from the index.
  4. symbols list contains class and function names.
  5. dependencies uses ProjectDependencyGraph.build() output.
  6. summaries maps file_path → one-line summary.
  7. indexed_at is the max last_updated timestamp across files.
  8. dep_graph.build() failure is non-fatal — files/symbols/summaries still returned.
  9. Never returns None under any circumstance.
 10. MemoryOrchestrator._load_intelligence() receives the is_populated flag.

Running:
    cd backend
    python -m pytest tests/test_context_orchestrator_get_project_state.py -v
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.intelligence.context_orchestrator import ContextOrchestrator
from app.intelligence.file_indexer import FileMetadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {"files", "symbols", "dependencies", "summaries", "indexed_at", "is_populated"}


def _make_file_meta(
    file_path: str,
    classes: list[str] | None = None,
    functions: list[str] | None = None,
    last_updated: str = "2026-01-01T00:00:00+00:00",
) -> FileMetadata:
    return FileMetadata(
        file_path=file_path,
        language="python",
        purpose=f"Purpose of {file_path}",
        classes=classes or [],
        functions=functions or [],
        imports=[],
        exports=[],
        dependencies=[],
        line_count=10,
        size_bytes=200,
        last_updated=last_updated,
        sprint_number=1,
    )


def _make_orchestrator(indexed_files: list[FileMetadata], dep_graph_result: dict | Exception | None = None) -> ContextOrchestrator:
    """Build a ContextOrchestrator with mocked collaborators."""
    indexer = MagicMock()
    indexer.get_project_index.return_value = indexed_files
    indexer.get_file_summary.return_value = "one-line summary"

    dep_graph = MagicMock()
    if isinstance(dep_graph_result, Exception):
        dep_graph.build.side_effect = dep_graph_result
    else:
        dep_graph.build.return_value = dep_graph_result or {}

    summarizer = MagicMock()
    summarizer.summarize_file.return_value = "one-line summary"
    summarizer.build_project_overview.return_value = "overview"
    summarizer.get_relevant_files.return_value = []

    return ContextOrchestrator(
        file_indexer=indexer,
        dependency_graph=dep_graph,
        code_summarizer=summarizer,
        knowledge_memory=MagicMock(),
        lesson_store=MagicMock(),
        artifact_manager=MagicMock(),
        workspace_manager=MagicMock(),
    )


# ---------------------------------------------------------------------------
# 1. Empty index → structured empty response
# ---------------------------------------------------------------------------

class TestGetProjectStateEmpty:

    def test_all_required_keys_present_when_empty(self):
        """All required keys must exist even when no files are indexed."""
        oc = _make_orchestrator(indexed_files=[])
        state = oc.get_project_state("proj-empty")
        assert _REQUIRED_KEYS.issubset(state.keys()), (
            f"Missing keys: {_REQUIRED_KEYS - state.keys()}"
        )

    def test_is_populated_false_when_empty(self):
        oc = _make_orchestrator(indexed_files=[])
        assert oc.get_project_state("proj-empty")["is_populated"] is False

    def test_files_empty_list_when_not_indexed(self):
        oc = _make_orchestrator(indexed_files=[])
        assert oc.get_project_state("proj-empty")["files"] == []

    def test_symbols_empty_list_when_not_indexed(self):
        oc = _make_orchestrator(indexed_files=[])
        assert oc.get_project_state("proj-empty")["symbols"] == []

    def test_never_returns_none(self):
        oc = _make_orchestrator(indexed_files=[])
        assert oc.get_project_state("proj-empty") is not None


# ---------------------------------------------------------------------------
# 2-7. Populated index
# ---------------------------------------------------------------------------

class TestGetProjectStatePopulated:

    def _state(self):
        files = [
            _make_file_meta("backend/app.py", classes=["App"], functions=["main()"], last_updated="2026-06-01T12:00:00+00:00"),
            _make_file_meta("backend/models.py", classes=["User"], functions=["get_user()"], last_updated="2026-06-02T08:00:00+00:00"),
        ]
        dep_result = {"backend/app.py": ["backend/models.py"]}
        oc = _make_orchestrator(files, dep_result)
        return oc.get_project_state("proj-pop")

    def test_is_populated_true(self):
        assert self._state()["is_populated"] is True

    def test_files_contains_paths(self):
        state = self._state()
        assert "backend/app.py" in state["files"]
        assert "backend/models.py" in state["files"]

    def test_symbols_contains_classes_and_functions(self):
        state = self._state()
        assert "App" in state["symbols"]
        assert "User" in state["symbols"]
        assert "main()" in state["symbols"]
        assert "get_user()" in state["symbols"]

    def test_dependencies_uses_dep_graph_output(self):
        state = self._state()
        assert state["dependencies"] == {"backend/app.py": ["backend/models.py"]}

    def test_summaries_keys_are_file_paths(self):
        state = self._state()
        assert "backend/app.py" in state["summaries"]
        assert "backend/models.py" in state["summaries"]

    def test_summaries_values_are_strings(self):
        state = self._state()
        for v in state["summaries"].values():
            assert isinstance(v, str)

    def test_indexed_at_is_max_last_updated(self):
        state = self._state()
        # max of the two timestamps should be the later one
        assert state["indexed_at"] == "2026-06-02T08:00:00+00:00"

    def test_all_required_keys_present(self):
        assert _REQUIRED_KEYS.issubset(self._state().keys())


# ---------------------------------------------------------------------------
# 8. dep_graph failure is non-fatal
# ---------------------------------------------------------------------------

class TestGetProjectStateDepGraphFailure:

    def test_dep_graph_failure_returns_empty_dependencies(self):
        """When dep_graph.build raises, dependencies is {} but other fields populated."""
        files = [_make_file_meta("main.py", classes=["App"])]
        oc = _make_orchestrator(files, dep_graph_result=RuntimeError("db locked"))
        state = oc.get_project_state("proj-depfail")

        assert state["is_populated"] is True
        assert "main.py" in state["files"]
        assert "App" in state["symbols"]
        assert state["dependencies"] == {}

    def test_indexer_failure_returns_empty_state(self):
        """When indexer.get_project_index raises, full empty dict is returned."""
        indexer = MagicMock()
        indexer.get_project_index.side_effect = RuntimeError("disk error")
        oc = ContextOrchestrator(
            file_indexer=indexer,
            dependency_graph=MagicMock(),
            code_summarizer=MagicMock(),
            knowledge_memory=MagicMock(),
            lesson_store=MagicMock(),
            artifact_manager=MagicMock(),
            workspace_manager=MagicMock(),
        )
        state = oc.get_project_state("proj-indexfail")
        assert state["is_populated"] is False
        assert _REQUIRED_KEYS.issubset(state.keys())


# ---------------------------------------------------------------------------
# 9. MemoryOrchestrator._load_intelligence receives is_populated
# ---------------------------------------------------------------------------

class TestMemoryOrchestratorIntegration:

    def test_load_intelligence_receives_is_populated_true(self):
        """_load_intelligence must forward get_project_state dict including is_populated."""
        from app.memory.orchestrator import MemoryOrchestrator

        files = [_make_file_meta("service.py", classes=["Service"])]
        oc = _make_orchestrator(files)

        mem_orch = MemoryOrchestrator.__new__(MemoryOrchestrator)
        mem_orch.context_orchestrator = oc

        result = mem_orch._load_intelligence("proj-mem")
        assert result.get("is_populated") is True
        assert "service.py" in result.get("files", [])

    def test_load_intelligence_returns_empty_when_no_files(self):
        """_load_intelligence must return {} / is_populated=False when index empty."""
        from app.memory.orchestrator import MemoryOrchestrator

        oc = _make_orchestrator(indexed_files=[])
        mem_orch = MemoryOrchestrator.__new__(MemoryOrchestrator)
        mem_orch.context_orchestrator = oc

        result = mem_orch._load_intelligence("proj-mem-empty")
        assert result.get("is_populated") is False
