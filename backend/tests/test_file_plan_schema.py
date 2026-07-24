import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.shared.schemas.file_plan_schema import PlannedFile


class PlannedFilePathNormalizationTests(unittest.TestCase):
    def test_leading_forward_slash_is_stripped(self) -> None:
        planned = PlannedFile(path="/api/users/register", responsible_stage="backend")
        self.assertEqual(planned.path, "api/users/register")

    def test_leading_backslash_is_stripped_and_normalized(self) -> None:
        planned = PlannedFile(path="\\backend\\routes\\auth.js", responsible_stage="backend")
        self.assertEqual(planned.path, "backend/routes/auth.js")

    def test_already_relative_path_is_unchanged(self) -> None:
        planned = PlannedFile(path="backend/models/user.py", responsible_stage="backend")
        self.assertEqual(planned.path, "backend/models/user.py")


if __name__ == "__main__":
    unittest.main()
