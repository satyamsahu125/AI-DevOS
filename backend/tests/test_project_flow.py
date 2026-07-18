import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.project.manager import ProjectManager
from app.shared.dto.project_request import ProjectRequest


class ProjectFlowTests(unittest.TestCase):
    def test_create_project_initializes_workspace_and_memory(self) -> None:
        manager = ProjectManager()
        response = manager.create_project(ProjectRequest(name="Demo Project", description="Demo"))
        self.assertEqual(response.name, "Demo Project")
        self.assertTrue(Path(response.workspace_path).exists())


if __name__ == "__main__":
    unittest.main()
