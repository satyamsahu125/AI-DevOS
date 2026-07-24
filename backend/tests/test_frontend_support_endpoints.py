import io
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.api.dependencies import get_event_log, get_project_file_manager, get_project_manager
from app.main import app
from app.memory.project_event_log import ProjectEventLog
from app.project.repository import ProjectRepository
from app.shared.models.project import Project
from app.workspace.manager import WorkspaceManager
from app.workspace.project_files import ProjectFileManager


class ProjectEventLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="event_log_test_"))
        self.log = ProjectEventLog(db_path=self.tmp_dir / "events.db")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_record_and_get_events_in_order(self) -> None:
        self.log.record("proj1", "Architect", "Architect started")
        self.log.record("proj1", "Architect", "Attempt 1 rejected", level="warning")
        self.log.record("proj1", "Architect", "Architect approved on attempt 2")

        events = self.log.get_events("proj1")

        self.assertEqual(len(events), 3)
        self.assertEqual([e.message for e in events], ["Architect started", "Attempt 1 rejected", "Architect approved on attempt 2"])
        self.assertEqual(events[1].level, "warning")

    def test_since_id_returns_only_new_events(self) -> None:
        self.log.record("proj1", "Architect", "first")
        first_id = self.log.get_events("proj1")[0].id
        self.log.record("proj1", "Architect", "second")

        events = self.log.get_events("proj1", since_id=first_id)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].message, "second")

    def test_events_are_isolated_per_project(self) -> None:
        self.log.record("proj-a", "Architect", "for a")
        self.log.record("proj-b", "Architect", "for b")

        self.assertEqual([e.message for e in self.log.get_events("proj-a")], ["for a"])
        self.assertEqual([e.message for e in self.log.get_events("proj-b")], ["for b"])

    def test_record_with_no_project_id_is_a_no_op(self) -> None:
        self.log.record("", "Architect", "should not be stored")
        self.assertEqual(self.log.get_events(""), [])


class FilesAndLogsEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="frontend_endpoints_test_"))
        self.workspace_manager = WorkspaceManager(self.tmp_dir / "temp-workspace")
        self.project_file_manager = ProjectFileManager(self.workspace_manager)
        self.event_log = ProjectEventLog(db_path=self.tmp_dir / "events.db")
        self.workspace_manager.create_workspace("proj1")

        self.project_repository = ProjectRepository(root=self.tmp_dir / "projects")
        self.project_repository.save(
            Project(project_id="proj1", name="Test Project", description="A test project.", workspace_path=str(self.tmp_dir))
        )
        fake_project_manager = SimpleNamespace(repository=self.project_repository)

        app.dependency_overrides[get_project_file_manager] = lambda: self.project_file_manager
        app.dependency_overrides[get_event_log] = lambda: self.event_log
        app.dependency_overrides[get_project_manager] = lambda: fake_project_manager
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.pop(get_project_file_manager, None)
        app.dependency_overrides.pop(get_event_log, None)
        app.dependency_overrides.pop(get_project_manager, None)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_list_files_reflects_real_written_files(self) -> None:
        self.project_file_manager.write_file("proj1", "backend", "main.py", "print('hi')")
        self.project_file_manager.write_file("proj1", "frontend", "src/App.jsx", "export default function App() {}")

        response = self.client.get("/projects/proj1/files")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["backend"], ["main.py"])
        self.assertEqual(body["frontend"], ["src/App.jsx"])

    def test_get_file_content_returns_real_content(self) -> None:
        self.project_file_manager.write_file("proj1", "backend", "main.py", "print('hi')")

        response = self.client.get("/projects/proj1/files/backend/main.py")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "print('hi')")

    def test_get_file_content_404_for_unknown_file(self) -> None:
        response = self.client.get("/projects/proj1/files/backend/does-not-exist.py")
        self.assertEqual(response.status_code, 404)

    def test_get_file_content_rejects_path_traversal(self) -> None:
        response = self.client.get("/projects/proj1/files/backend/..%2F..%2F..%2Fsecrets.txt")
        self.assertIn(response.status_code, (400, 404))

    def test_logs_endpoint_returns_recorded_events(self) -> None:
        self.event_log.record("proj1", "Architect", "Architect started")
        self.event_log.record("proj1", "Architect", "Architect approved on attempt 1")

        response = self.client.get("/projects/proj1/logs")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 2)
        self.assertEqual(body[0]["message"], "Architect started")

    def test_logs_endpoint_since_id_filters_correctly(self) -> None:
        self.event_log.record("proj1", "Architect", "first")
        first_id = self.client.get("/projects/proj1/logs").json()[0]["id"]
        self.event_log.record("proj1", "Architect", "second")

        response = self.client.get(f"/projects/proj1/logs?since_id={first_id}")

        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["message"], "second")

    def test_run_instructions_reflects_real_written_files(self) -> None:
        self.project_file_manager.write_file("proj1", "backend", "main.py", "print('hi')")

        response = self.client.get("/projects/proj1/run-instructions")

        self.assertEqual(response.status_code, 200)
        markdown = response.json()["markdown"]
        self.assertIn("main.py", markdown)
        self.assertIn("python", markdown)

    def test_run_instructions_404_for_unknown_project(self) -> None:
        response = self.client.get("/projects/does-not-exist/run-instructions")
        self.assertEqual(response.status_code, 404)

    def test_download_returns_zip_with_generated_files_and_run_instructions(self) -> None:
        self.project_file_manager.write_file("proj1", "backend", "main.py", "print('hi')")
        self.project_file_manager.write_file("proj1", "frontend", "src/App.jsx", "export default function App() {}")

        response = self.client.get("/projects/proj1/download")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        names = set(archive.namelist())
        self.assertIn("backend/main.py", names)
        self.assertIn("frontend/src/App.jsx", names)
        self.assertIn("RUN_INSTRUCTIONS.md", names)
        self.assertEqual(archive.read("backend/main.py").decode("utf-8"), "print('hi')")

    def test_download_404_when_nothing_generated_yet(self) -> None:
        response = self.client.get("/projects/proj1/download")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
