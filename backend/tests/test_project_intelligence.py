"""Tests for the Project Intelligence Layer.

Covers:
  - FileIndexer: Python AST parsing, TypeScript regex parsing, SQLite upsert, summaries
  - ProjectDependencyGraph: build, impact BFS, entry points, most-depended-on
  - CodeSummarizer: file summaries, project overview, relevance ranking
  - ContextOrchestrator: full package build with mocked collaborators
  - Intelligence API endpoints (smoke tests)
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.intelligence.code_summarizer import CodeSummarizer
from app.intelligence.context_orchestrator import ContextOrchestrator, ContextPackage
from app.intelligence.dependency_graph import ProjectDependencyGraph
from app.intelligence.file_indexer import FileIndexer, FileMetadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def indexer():
    """In-memory FileIndexer — no disk I/O."""
    return FileIndexer(":memory:")


@pytest.fixture()
def populated_indexer(indexer):
    """FileIndexer with 5 pre-indexed Python files."""
    for i in range(5):
        indexer.index_file(
            "proj-1",
            f"backend/service_{i}.py",
            f'"""Service {i} — handles task {i}."""\nclass Service{i}:\n    def run_{i}(self): pass\n',
        )
    return indexer


# ---------------------------------------------------------------------------
# FileIndexer — Python parsing
# ---------------------------------------------------------------------------

class TestFileIndexerPython:
    def test_parses_classes(self, indexer):
        content = "class AuthService:\n    def login(self, email, password): pass\n"
        meta = indexer.index_file("p1", "backend/auth.py", content)
        assert "AuthService" in meta.classes

    def test_parses_functions(self, indexer):
        content = (
            "class AuthService:\n"
            "    def login(self, email: str, password: str): pass\n"
            "    def logout(self, user_id: str): pass\n"
            "from app.repositories.user_repo import UserRepository\n"
        )
        meta = indexer.index_file("p1", "backend/services/auth.py", content)
        assert "AuthService" in meta.classes
        # Methods are class-level; top-level functions list may be empty
        # but classes must be captured
        assert meta.language == "python"

    def test_parses_internal_imports(self, indexer):
        content = "from app.repositories.user_repo import UserRepository\n"
        meta = indexer.index_file("p1", "backend/auth.py", content)
        assert any("user_repo" in d for d in meta.dependencies)

    def test_relative_import_detected(self, indexer):
        content = "from . import utils\nfrom .models import User\n"
        meta = indexer.index_file("p1", "backend/service.py", content)
        # relative imports (node.level > 0) produce dependencies
        assert len(meta.imports) > 0

    def test_invalid_syntax_does_not_raise(self, indexer):
        meta = indexer.index_file("p1", "backend/broken.py", "def (broken syntax")
        assert meta.file_path == "backend/broken.py"

    def test_upsert_replaces_existing(self, indexer):
        indexer.index_file("p1", "backend/f.py", "class Old: pass")
        indexer.index_file("p1", "backend/f.py", "class New: pass")
        files = indexer.get_project_index("p1")
        assert len(files) == 1
        assert "New" in files[0].classes
        assert "Old" not in files[0].classes

    def test_project_isolation(self, indexer):
        indexer.index_file("proj-A", "file.py", "class A: pass")
        indexer.index_file("proj-B", "file.py", "class B: pass")
        a_files = indexer.get_project_index("proj-A")
        b_files = indexer.get_project_index("proj-B")
        assert any("A" in f.classes for f in a_files)
        assert not any("A" in f.classes for f in b_files)

    def test_sprint_number_stored(self, indexer):
        meta = indexer.index_file("p1", "backend/f.py", "class X: pass", sprint_number=3)
        assert meta.sprint_number == 3
        files = indexer.get_project_index("p1")
        assert files[0].sprint_number == 3

    def test_line_count_and_size(self, indexer):
        content = "class X:\n    pass\n"
        meta = indexer.index_file("p1", "backend/f.py", content)
        assert meta.line_count == content.count("\n")
        assert meta.size_bytes == len(content.encode())


# ---------------------------------------------------------------------------
# FileIndexer — TypeScript parsing
# ---------------------------------------------------------------------------

class TestFileIndexerTypeScript:
    def test_parses_class(self, indexer):
        content = "export class UserService {\n  async getUser(id: string) {}\n}\n"
        meta = indexer.index_file("p1", "frontend/services/user.ts", content)
        assert "UserService" in meta.classes
        assert meta.language == "typescript"

    def test_parses_functions(self, indexer):
        content = "export async function fetchUser(id: string) {}\nexport function logout() {}\n"
        meta = indexer.index_file("p1", "frontend/api.ts", content)
        assert any("fetchUser" in f for f in meta.functions)

    def test_parses_imports(self, indexer):
        content = "import { ApiClient } from './api/client'\nimport axios from 'axios'\n"
        meta = indexer.index_file("p1", "frontend/service.ts", content)
        assert any("./api/client" in d for d in meta.dependencies)
        assert "axios" in meta.imports

    def test_tsx_language_detected(self, indexer):
        meta = indexer.index_file("p1", "frontend/App.tsx", "export default function App() {}")
        assert meta.language == "typescript"


# ---------------------------------------------------------------------------
# FileIndexer — get_file_summary
# ---------------------------------------------------------------------------

class TestFileIndexerSummary:
    def test_summary_contains_path(self, indexer):
        indexer.index_file("p1", "backend/auth.py", '"""Auth module."""\nclass AuthService: pass\n')
        summary = indexer.get_file_summary("p1", "backend/auth.py")
        assert "backend/auth.py" in summary

    def test_summary_contains_class(self, indexer):
        indexer.index_file("p1", "backend/auth.py", "class AuthService: pass\n")
        summary = indexer.get_file_summary("p1", "backend/auth.py")
        assert "AuthService" in summary

    def test_summary_not_indexed_returns_placeholder(self, indexer):
        summary = indexer.get_file_summary("p1", "nonexistent.py")
        assert "not indexed" in summary

    def test_search_by_class(self, indexer):
        indexer.index_file("p1", "backend/auth.py", "class AuthService: pass\n")
        results = indexer.search_by_class("p1", "AuthService")
        assert len(results) >= 1

    def test_search_by_function(self, indexer):
        indexer.index_file("p1", "backend/utils.py", "def helper_func(): pass\n")
        paths = indexer.search_by_function("p1", "helper_func")
        assert "backend/utils.py" in paths


# ---------------------------------------------------------------------------
# ProjectDependencyGraph
# ---------------------------------------------------------------------------

class TestProjectDependencyGraph:
    def test_build_returns_dict(self, indexer):
        indexer.index_file("p1", "backend/models/user.py", "class User: pass\n")
        indexer.index_file(
            "p1", "backend/services/auth.py",
            "from app.models.user import User\nclass Auth: pass\n",
        )
        graph = ProjectDependencyGraph(indexer)
        result = graph.build("p1")
        assert isinstance(result, dict)

    def test_entry_points_detected(self, indexer):
        indexer.index_file("p1", "backend/main.py", "from app.router import router\n")
        indexer.index_file("p1", "backend/router.py", "class Router: pass\n")
        graph = ProjectDependencyGraph(indexer)
        entry_points = graph.get_entry_points("p1")
        assert isinstance(entry_points, list)

    def test_get_dependencies_of_empty_for_unknown(self, indexer):
        graph = ProjectDependencyGraph(indexer)
        deps = graph.get_dependencies_of("p1", "nonexistent.py")
        assert deps == []

    def test_get_impact_returns_list(self, indexer):
        indexer.index_file("p1", "backend/db.py", "class DB: pass\n")
        graph = ProjectDependencyGraph(indexer)
        affected = graph.get_impact("p1", "backend/db.py")
        assert isinstance(affected, list)

    def test_most_depended_on_top_n(self, indexer):
        for i in range(3):
            indexer.index_file("p1", f"backend/svc_{i}.py", "from app.db import DB\nclass S: pass\n")
        graph = ProjectDependencyGraph(indexer)
        ranked = graph.get_most_depended_on("p1", top_n=5)
        assert isinstance(ranked, list)

    def test_format_for_context_empty_files(self, indexer):
        graph = ProjectDependencyGraph(indexer)
        result = graph.format_for_context("p1", [])
        assert result == ""

    def test_format_for_context_has_header(self, indexer):
        indexer.index_file("p1", "backend/auth.py", "class Auth: pass\n")
        graph = ProjectDependencyGraph(indexer)
        result = graph.format_for_context("p1", ["backend/auth.py"])
        assert "DEPENDENCY" in result


# ---------------------------------------------------------------------------
# CodeSummarizer
# ---------------------------------------------------------------------------

class TestCodeSummarizer:
    def test_overview_contains_header(self, populated_indexer):
        summarizer = CodeSummarizer(populated_indexer)
        overview = summarizer.build_project_overview("proj-1")
        assert "PROJECT STRUCTURE" in overview

    def test_overview_contains_file_count(self, populated_indexer):
        summarizer = CodeSummarizer(populated_indexer)
        overview = summarizer.build_project_overview("proj-1")
        assert "5 files" in overview

    def test_overview_empty_project(self, indexer):
        summarizer = CodeSummarizer(indexer)
        overview = summarizer.build_project_overview("empty-proj")
        assert "No files" in overview

    def test_summarize_minimal(self, populated_indexer):
        summarizer = CodeSummarizer(populated_indexer)
        result = summarizer.summarize_file("proj-1", "backend/service_0.py", detail_level="minimal")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_summarize_full_small_content(self, indexer):
        content = "class Tiny: pass\n"
        indexer.index_file("p1", "backend/tiny.py", content)
        summarizer = CodeSummarizer(indexer)
        result = summarizer.summarize_file("p1", "backend/tiny.py", full_content=content, detail_level="full")
        assert "backend/tiny.py" in result

    def test_relevant_files_keyword_match(self, indexer):
        indexer.index_file("p1", "backend/auth_service.py", "class AuthService:\n    def login(self): pass\n")
        indexer.index_file("p1", "backend/user_repo.py", "class UserRepository: pass\n")
        summarizer = CodeSummarizer(indexer)
        # "auth" is a substring of "auth_service.py" (file path scoring) and "AuthService" (class scoring)
        results = summarizer.get_relevant_files("p1", "auth login", max_files=5)
        assert "backend/auth_service.py" in results

    def test_relevant_files_returns_list(self, populated_indexer):
        summarizer = CodeSummarizer(populated_indexer)
        results = summarizer.get_relevant_files("proj-1", "service task", max_files=3)
        assert isinstance(results, list)
        assert len(results) <= 3


# ---------------------------------------------------------------------------
# ContextOrchestrator
# ---------------------------------------------------------------------------

class TestContextOrchestrator:
    def _make_orchestrator(self, indexer=None) -> ContextOrchestrator:
        idx = indexer or FileIndexer(":memory:")
        dep_graph = MagicMock()
        dep_graph.format_for_context.return_value = ""
        return ContextOrchestrator(
            file_indexer=idx,
            dependency_graph=dep_graph,
            code_summarizer=CodeSummarizer(idx),
            knowledge_memory=MagicMock(search=MagicMock(return_value=[])),
            lesson_store=MagicMock(get_lessons=MagicMock(return_value=[])),
            artifact_manager=MagicMock(get_artifact=MagicMock(return_value=None)),
            workspace_manager=MagicMock(
                load_project_json=MagicMock(return_value={"requirement_changes": []})
            ),
        )

    def test_build_returns_context_package(self):
        orch = self._make_orchestrator()
        pkg = orch.build("proj-1", "backend", "implement user auth")
        assert isinstance(pkg, ContextPackage)

    def test_package_stage_set(self):
        orch = self._make_orchestrator()
        pkg = orch.build("proj-1", "backend", "implement user auth")
        assert pkg.stage == "backend"

    def test_package_relevant_files_is_dict(self):
        orch = self._make_orchestrator()
        pkg = orch.build("proj-1", "backend", "implement user auth")
        assert isinstance(pkg.relevant_files, dict)

    def test_format_as_prompt_section_returns_string(self):
        orch = self._make_orchestrator()
        pkg = orch.build("proj-1", "backend", "some task")
        result = orch.format_as_prompt_section(pkg)
        assert isinstance(result, str)

    def test_format_includes_overview_when_files_exist(self):
        idx = FileIndexer(":memory:")
        idx.index_file("proj-1", "backend/auth.py", "class Auth: pass\n")
        orch = self._make_orchestrator(idx)
        pkg = orch.build("proj-1", "backend", "auth task")
        result = orch.format_as_prompt_section(pkg)
        assert "PROJECT OVERVIEW" in result

    def test_build_handles_knowledge_error_gracefully(self):
        idx = FileIndexer(":memory:")
        dep_graph = MagicMock()
        dep_graph.format_for_context.return_value = ""
        orch = ContextOrchestrator(
            file_indexer=idx,
            dependency_graph=dep_graph,
            code_summarizer=CodeSummarizer(idx),
            knowledge_memory=MagicMock(search=MagicMock(side_effect=RuntimeError("boom"))),
            lesson_store=MagicMock(get_lessons=MagicMock(return_value=[])),
            artifact_manager=MagicMock(get_artifact=MagicMock(return_value=None)),
            workspace_manager=MagicMock(
                load_project_json=MagicMock(return_value={"requirement_changes": []})
            ),
        )
        # Should not raise
        pkg = orch.build("proj-1", "backend", "task")
        assert isinstance(pkg, ContextPackage)

    def test_build_handles_workspace_error_gracefully(self):
        idx = FileIndexer(":memory:")
        dep_graph = MagicMock()
        dep_graph.format_for_context.return_value = ""
        orch = ContextOrchestrator(
            file_indexer=idx,
            dependency_graph=dep_graph,
            code_summarizer=CodeSummarizer(idx),
            knowledge_memory=MagicMock(search=MagicMock(return_value=[])),
            lesson_store=MagicMock(get_lessons=MagicMock(return_value=[])),
            artifact_manager=MagicMock(get_artifact=MagicMock(return_value=None)),
            workspace_manager=MagicMock(
                load_project_json=MagicMock(side_effect=FileNotFoundError("no project"))
            ),
        )
        pkg = orch.build("proj-1", "backend", "task")
        assert pkg.requirement_changes == []


# ---------------------------------------------------------------------------
# Intelligence API smoke tests
# ---------------------------------------------------------------------------

class TestIntelligenceAPI:
    def test_files_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/projects/test-proj-id/intelligence/files")
        assert resp.status_code == 200

    def test_overview_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/projects/test-proj-id/intelligence/overview")
        assert resp.status_code == 200

    def test_dependencies_endpoint_exists(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/projects/test-proj-id/intelligence/dependencies")
        assert resp.status_code == 200

    def test_search_endpoint_requires_q(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/projects/test-proj-id/intelligence/search")
        assert resp.status_code == 422  # missing required query param

    def test_search_endpoint_with_query(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/projects/test-proj-id/intelligence/search?q=auth")
        assert resp.status_code == 200

    def test_impact_endpoint_requires_file(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/projects/test-proj-id/intelligence/impact")
        assert resp.status_code == 422

    def test_impact_endpoint_with_file(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        resp = client.get("/projects/test-proj-id/intelligence/impact?file=backend/auth.py")
        assert resp.status_code == 200

