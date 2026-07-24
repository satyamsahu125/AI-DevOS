import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory.lesson_store import Lesson, LessonStore, new_lesson_id


class LessonStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="lesson_store_test_"))
        self.store = LessonStore(db_path=self._tmp_dir / "lessons.db")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _lesson(self, **overrides) -> Lesson:
        defaults = dict(
            lesson_id=new_lesson_id(),
            stage="WriteRequirements",
            project_id="proj-a",
            what_worked="Naming the target user explicitly sped up approval",
            what_failed="Vague acceptance criteria got rejected",
            reviewer_said="acceptance criteria must be testable",
            retry_count_when_learned=1,
            created_at=datetime.now(timezone.utc),
        )
        defaults.update(overrides)
        return Lesson(**defaults)

    def test_add_lesson_and_get_lessons_round_trip(self) -> None:
        lesson = self._lesson()
        self.store.add_lesson(lesson)

        lessons = self.store.get_lessons("WriteRequirements", "proj-a")

        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0].lesson_id, lesson.lesson_id)
        self.assertEqual(lessons[0].what_worked, lesson.what_worked)
        self.assertEqual(lessons[0].reviewer_said, lesson.reviewer_said)

    def test_get_lessons_scopes_to_exact_project(self) -> None:
        self.store.add_lesson(self._lesson(project_id="proj-a"))
        self.store.add_lesson(self._lesson(project_id="proj-b"))

        lessons = self.store.get_lessons("WriteRequirements", "proj-a")

        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0].project_id, "proj-a")

    def test_get_all_lessons_returns_lessons_across_projects(self) -> None:
        self.store.add_lesson(self._lesson(project_id="proj-a"))
        self.store.add_lesson(self._lesson(project_id="proj-b"))

        lessons = self.store.get_all_lessons("WriteRequirements")

        self.assertEqual({lesson.project_id for lesson in lessons}, {"proj-a", "proj-b"})

    def test_prune_old_lessons_removes_only_old_ones(self) -> None:
        old_lesson = self._lesson(created_at=datetime.now(timezone.utc) - timedelta(days=200))
        recent_lesson = self._lesson(created_at=datetime.now(timezone.utc))
        self.store.add_lesson(old_lesson)
        self.store.add_lesson(recent_lesson)

        removed = self.store.prune_old_lessons(older_than_days=90)

        self.assertEqual(removed, 1)
        remaining = self.store.get_all_lessons("WriteRequirements")
        self.assertEqual([lesson.lesson_id for lesson in remaining], [recent_lesson.lesson_id])

    def test_export_lessons_renders_markdown(self) -> None:
        self.store.add_lesson(self._lesson())

        markdown = self.store.export_lessons("WriteRequirements")

        self.assertIn("## Lessons: WriteRequirements", markdown)
        self.assertIn("What worked", markdown)
        self.assertIn("acceptance criteria must be testable", markdown)

    def test_export_lessons_handles_empty_stage(self) -> None:
        markdown = self.store.export_lessons("NeverUsedStage")
        self.assertIn("No lessons recorded yet", markdown)


if __name__ == "__main__":
    unittest.main()
