"""Unit tests for Interactive Q&A (ClarificationAgent Phase A & Phase B)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.shared.enums.project_state import ProjectState
from app.shared.schemas.qa_session_schema import Question, QuestionOption, QASession, QuestionSet
from app.workspace.manager import WorkspaceManager


class InteractiveQATests(unittest.TestCase):
    def test_qa_session_schema(self) -> None:
        """Verify QASession and QuestionSet models validate correctly."""
        q1 = Question(
            index=0,
            question="What type of app is this?",
            category="WHAT_IS_IT",
            priority="CRITICAL",
            options=[
                QuestionOption(value="web_calc", label="Web Calculator"),
                QuestionOption(value="mobile_calc", label="Mobile Calculator"),
            ],
            allows_custom=True,
            skippable=False,
        )
        qset = QuestionSet(questions=[q1])
        self.assertEqual(len(qset.questions), 1)

        session = QASession(
            status="pending",
            total_questions=1,
            answered=0,
            questions=[q1],
            answers=[],
            completed=False,
        )
        self.assertEqual(session.status, "pending")
        self.assertFalse(session.completed)

    def test_workspace_manager_qa_session(self) -> None:
        """Verify WorkspaceManager Q&A session persistence methods."""
        wm = WorkspaceManager()
        project_id = "test-qa-proj-123"
        wm.create_workspace(project_id, "Test Project", "Description")

        q1 = Question(
            index=0,
            question="Who are the primary users?",
            category="WHO_ARE_USERS",
            priority="CRITICAL",
            options=[QuestionOption(value="personal", label="Personal Use")],
            allows_custom=True,
            skippable=False,
        )
        q2 = Question(
            index=1,
            question="Is auth required?",
            category="WHO_ARE_USERS",
            priority="MAJOR",
            options=[QuestionOption(value="no", label="No Auth")],
            allows_custom=True,
            skippable=True,
        )

        wm.save_qa_questions(project_id, [q1, q2])
        qa = wm.get_qa_session(project_id)
        self.assertEqual(qa.get("total_questions"), 2)
        self.assertEqual(qa.get("answered"), 0)

        wm.save_qa_answer(project_id, 0, "Anyone on the web — personal use")
        qa_after_1 = wm.get_qa_session(project_id)
        self.assertEqual(qa_after_1.get("answered"), 1)
        self.assertEqual(qa_after_1["answers"][0]["answer"], "Anyone on the web — personal use")

        wm.skip_qa_question(project_id, 1)
        qa_after_2 = wm.get_qa_session(project_id)
        self.assertEqual(qa_after_2.get("answered"), 2)

        wm.mark_qa_complete(project_id)
        qa_complete = wm.get_qa_session(project_id)
        self.assertTrue(qa_complete.get("completed"))
        self.assertEqual(qa_complete.get("status"), "complete")


if __name__ == "__main__":
    unittest.main()
