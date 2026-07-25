import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.backend import BackendDeveloperAgent
from app.agents.frontend import FrontendDeveloperAgent
from app.execution.file_validator import FileValidator
from app.execution.project_writer import ProjectWriter
from app.shared.schemas.file_plan_schema import FilePlan, FileSpec
from app.workspace.manager import WorkspaceManager


class FilePlannerAndWriterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_file_planner_"))
        self.workspace_manager = WorkspaceManager(root=self.tmp_dir)
        self.writer = ProjectWriter(self.workspace_manager)
        self.validator = FileValidator()

    def test_project_writer_creates_and_reads_files(self) -> None:
        proj_id = "test-proj-writer"
        self.writer.initialize_project(proj_id)
        project_dir = self.writer.get_project_dir(proj_id)
        self.assertTrue((project_dir / "backend").exists())
        self.assertTrue((project_dir / "frontend").exists())

        written = self.writer.write_file(proj_id, "backend/main.py", "print('hello')\n", attempt=1)
        self.assertTrue(self.writer.file_exists(proj_id, "backend/main.py"))
        content = self.writer.read_file(proj_id, "backend/main.py")
        self.assertEqual(content, "print('hello')\n")
        files = self.writer.list_files(proj_id)
        self.assertIn("backend/main.py", files)

    def test_file_validator_validates_python_and_json(self) -> None:
        res_py = self.validator.validate("test.py", "def foo():\n    return 42\n", "python")
        self.assertTrue(res_py.passed)

        res_bad_py = self.validator.validate("bad.py", "def foo(\n", "python")
        self.assertFalse(res_bad_py.passed)
        self.assertTrue(len(res_bad_py.errors) > 0)

        res_json = self.validator.validate("test.json", '{\n  "key": "value"\n}\n', "json")
        self.assertTrue(res_json.passed)

    def test_file_plan_schema_validates(self) -> None:
        file_spec = FileSpec(
            file_path="backend/models/todo.py",
            purpose="Define Todo SQLAlchemy model",
            language="python",
            file_type="model",
            required_imports=["sqlalchemy"],
            required_classes=[{"name": "Todo", "base": "Base"}],
            exports=["Todo"],
        )
        plan = FilePlan(
            project_id="p1",
            sprint_number=1,
            sprint_name="Foundation",
            generation_order=["backend/models/todo.py"],
            files={"backend/models/todo.py": file_spec},
            total_files=1,
        )
        self.assertEqual(plan.files["backend/models/todo.py"].language, "python")
        self.assertEqual(plan.total_files, 1)


if __name__ == "__main__":
    unittest.main()
