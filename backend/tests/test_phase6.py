from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.execution.project_reader import ProjectReader
from app.execution.project_writer import ProjectWriter
from app.workspace.manager import WorkspaceManager
from app.prompt.qa_builder import QAPromptBuilder
from app.prompt.devops_builder import DevOpsPromptBuilder
from app.prompt.documentation_builder import DocumentationPromptBuilder
from app.actions.write_qa_report import WriteQAReportAction
from app.actions.write_deployment import WriteDeploymentAction
from app.actions.write_documentation import WriteDocumentationAction
from fastapi.testclient import TestClient
from app.main import app


class DummyLLM:
    def __init__(self, response: str) -> None:
        self.response = response

    def generate_text(self, prompt: str, system_prompt: str = "", max_tokens: int = 4096) -> str:
        return self.response


class Phase6Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace_manager = WorkspaceManager()
        self.project_writer = ProjectWriter(self.workspace_manager)
        self.project_reader = ProjectReader(self.workspace_manager)
        self.project_id = "test-phase6-proj"

        # Initialize dummy project structure
        self.project_writer.initialize_project(self.project_id)
        self.project_writer.write_file(
            self.project_id,
            "backend/main.py",
            "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health():\n    return {'status': 'ok'}\n",
        )
        self.project_writer.write_file(
            self.project_id,
            "backend/routers/auth.py",
            "from fastapi import APIRouter\nrouter = APIRouter()\n@router.post('/api/v1/auth/login')\ndef login():\n    pass\n",
        )
        self.project_writer.write_file(
            self.project_id,
            "backend/requirements.txt",
            "fastapi\nuvicorn\nsqlalchemy\npytest\n",
        )

    def test_project_reader_reads_backend_files(self) -> None:
        files = self.project_reader.read_all_backend_files(self.project_id)
        self.assertIn("backend/main.py", files)
        self.assertIn("backend/routers/auth.py", files)

    def test_project_reader_detects_routes(self) -> None:
        routes = self.project_reader.get_api_routes(self.project_id)
        methods = [r["method"] for r in routes]
        paths = [r["path"] for r in routes]
        self.assertIn("GET", methods)
        self.assertIn("POST", methods)
        self.assertIn("/health", paths)
        self.assertIn("/api/v1/auth/login", paths)

    def test_project_reader_detects_tech_stack(self) -> None:
        stack = self.project_reader.get_tech_stack(self.project_id)
        self.assertTrue(stack["has_fastapi"])
        self.assertTrue(stack["uses_sqlalchemy"])
        self.assertEqual(stack["backend_language"], "python")

    def test_qa_agent_produces_parseable_file_blocks(self) -> None:
        mock_response = (
            "===FILE: tests/conftest.py===\n"
            "import pytest\n"
            "@pytest.fixture\n"
            "def client(): pass\n"
            "===END===\n\n"
            "===FILE: tests/test_auth.py===\n"
            "def test_login(): assert True\n"
            "===END==="
        )
        llm = DummyLLM(mock_response)
        action = WriteQAReportAction(
            project_writer=self.project_writer,
            project_reader=self.project_reader,
        )
        out = action.run(self.project_id, llm)
        self.assertIn("tests/conftest.py", out.structured["test_files_written"])
        self.assertIn("tests/test_auth.py", out.structured["test_files_written"])
        self.assertTrue(self.project_writer.file_exists(self.project_id, "tests/conftest.py"))
        self.assertTrue(self.project_writer.file_exists(self.project_id, "tests/test_auth.py"))

    def test_devops_agent_produces_dockerfile(self) -> None:
        mock_response = (
            "===FILE: Dockerfile===\n"
            "FROM python:3.11-slim\n"
            "WORKDIR /app\n"
            "===END===\n\n"
            "===FILE: docker-compose.yml===\n"
            "version: '3.9'\n"
            "services:\n"
            "  backend:\n"
            "    image: test\n"
            "===END===\n\n"
            "===FILE: .env.example===\n"
            "DATABASE_URL=postgresql://user:pass@localhost/db\n"
            "===END==="
        )
        llm = DummyLLM(mock_response)
        action = WriteDeploymentAction(
            project_writer=self.project_writer,
            project_reader=self.project_reader,
        )
        out = action.run(self.project_id, llm)
        self.assertTrue(out.structured["has_dockerfile"])
        self.assertTrue(out.structured["has_compose"])
        self.assertTrue(self.project_writer.file_exists(self.project_id, "Dockerfile"))
        self.assertTrue(self.project_writer.file_exists(self.project_id, "docker-compose.yml"))
        self.assertTrue(self.project_writer.file_exists(self.project_id, ".env.example"))

    def test_documentation_agent_produces_readme(self) -> None:
        mock_response = (
            "# Test Project\n\n"
            "> A test project\n\n"
            "## Features\n- Auth\n\n"
            "## Tech Stack\n- Python\n\n"
            "## Prerequisites\n- Docker\n\n"
            "## Getting Started\n\n### Option 1: Docker\n```bash\ndocker-compose up\n```\n\n"
            "## Environment Variables\n| Var | Desc |\n\n"
            "## API Documentation\n| GET | /health |\n\n"
            "## Running Tests\npytest\n\n"
            "## Project Structure\nbackend/\n\n"
            "## Contributing\nFork it\n\n"
            "## License\nMIT"
        )
        llm = DummyLLM(mock_response)
        action = WriteDocumentationAction(
            project_writer=self.project_writer,
            project_reader=self.project_reader,
        )
        out = action.run(self.project_id, llm)
        self.assertEqual(out.structured["file_written"], "README.md")
        self.assertTrue(self.project_writer.file_exists(self.project_id, "README.md"))

    def test_readme_contains_installation_section(self) -> None:
        mock_response = "# App\n\n## Getting Started\nInstall via pip"
        llm = DummyLLM(mock_response)
        action = WriteDocumentationAction(
            project_writer=self.project_writer,
            project_reader=self.project_reader,
        )
        out = action.run(self.project_id, llm)
        self.assertTrue(out.structured["has_installation"])

    def test_download_endpoint_returns_zip(self) -> None:
        from app.api.dependencies import get_project_file_manager, get_project_manager, get_workspace_manager
        from app.project.repository import ProjectRepository
        from app.shared.models.project import Project
        from app.workspace.project_files import ProjectFileManager
        from types import SimpleNamespace

        repo = ProjectRepository(root=Path(self.workspace_manager.root) / "projects")
        repo.save(Project(project_id=self.project_id, name="Test Phase 6 Proj", description="Test", workspace_path=str(self.workspace_manager.get_workspace_path(self.project_id))))
        fake_manager = SimpleNamespace(repository=repo)

        app.dependency_overrides[get_workspace_manager] = lambda: self.workspace_manager
        app.dependency_overrides[get_project_file_manager] = lambda: ProjectFileManager(self.workspace_manager)
        app.dependency_overrides[get_project_manager] = lambda: fake_manager
        try:
            client = TestClient(app)
            res = client.get(f"/projects/{self.project_id}/download")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.headers["content-type"], "application/zip")
            self.assertIn("test-phase-6-proj.zip", res.headers["content-disposition"])
        finally:
            app.dependency_overrides.pop(get_workspace_manager, None)
            app.dependency_overrides.pop(get_project_file_manager, None)
            app.dependency_overrides.pop(get_project_manager, None)
