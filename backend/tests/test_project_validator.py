"""Unit tests for ProjectValidator (Phase 7)."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from app.execution.project_validator import ProjectValidator


class ProjectValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

        self.mock_workspace = MagicMock()
        self.mock_workspace.get_workspace_path.return_value = self.root

        self.validator = ProjectValidator(self.mock_workspace)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_returns_failed_result_when_project_dir_missing(self) -> None:
        result = self.validator.validate("test-project", skip_install=True)
        self.assertFalse(result.passed)
        self.assertIn("not found", result.error_summary)

    def test_compilation_passes_for_valid_python_files(self) -> None:
        proj_dir = self.root / "project" / "backend"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "main.py").write_text("print('hello world')", encoding="utf-8")

        result = self.validator.validate("test-project", skip_install=True)
        self.assertTrue(result.steps["compile"].passed)

    def test_compilation_fails_for_invalid_syntax(self) -> None:
        proj_dir = self.root / "project" / "backend"
        proj_dir.mkdir(parents=True, exist_ok=True)
        (proj_dir / "bad.py").write_text("def broken_syntax(:", encoding="utf-8")

        result = self.validator.validate("test-project", skip_install=True)
        self.assertFalse(result.steps["compile"].passed)
        self.assertFalse(result.passed)
        self.assertTrue(len(result.compile_errors) > 0)


if __name__ == "__main__":
    unittest.main()
