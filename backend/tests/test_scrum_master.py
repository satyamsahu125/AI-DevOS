"""Unit tests for ScrumMasterAgent (NEW AGENT)."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agents.scrum_master import ScrumMasterAgent
from app.llm.llm_response import LLMResponse


class ScrumMasterAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_llm = MagicMock()
        response_text = """{
            "sprint_number": 1,
            "sprint_name": "Sprint 1",
            "sprint_goal": "Deliver MVP auth system",
            "definition_of_done": ["All unit tests pass", "Code reviewed"],
            "tasks": [
                {
                    "task_id": "TASK-001",
                    "title": "Create User model",
                    "user_story_ref": "US-001",
                    "story_points": 3,
                    "assigned_agent": "backend",
                    "depends_on": [],
                    "acceptance_criteria": ["Model defined in SQLAlchemy"],
                    "risk_level": "low",
                    "parallelizable": true
                }
            ],
            "critical_path": ["TASK-001"],
            "total_story_points": 3,
            "blocked_tasks": [],
            "parallelizable_tasks": [["TASK-001"]],
            "risk_flags": [],
            "human_review_required": [],
            "anything_unclear": ""
        }"""
        self.mock_llm.generate_text.return_value = LLMResponse(
            response_id="res-1",
            provider="mock",
            model="mock-model",
            content=response_text,
        )

        self.agent = ScrumMasterAgent(llm_manager=self.mock_llm)

    def test_execute_generates_valid_scrum_plan(self) -> None:
        context = SimpleNamespace(content="Build auth system")
        output = self.agent.execute(context)
        self.assertIn("Deliver MVP auth system", output.content)
        self.assertEqual(output.structured_content["sprint_goal"], "Deliver MVP auth system")


if __name__ == "__main__":
    unittest.main()
