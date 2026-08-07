from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..actions.base_action import BaseAction
from ..actions.write_qa_report import WriteQAReportAction
from ..execution.file_validator import FileValidator
from ..execution.project_reader import ProjectReader
from ..execution.project_writer import ProjectWriter
from ..llm.manager import LLMManager
from ..prompt.qa_builder import QAPromptBuilder
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt for sprint QA
# ---------------------------------------------------------------------------

_SPRINT_QA_SYSTEM_PROMPT = """\
You are a QA Engineer testing a software sprint increment.

You receive:
- The file plan (what files were built this sprint)
- The architecture (design decisions)
- The user stories (acceptance criteria)

Your job is to produce a structured test report:

{
  "passed": true | false,
  "total_tests": <integer>,
  "failed_tests": <integer>,
  "failures": [
    {
      "test": "<test name or scenario>",
      "reason": "<why it failed>",
      "file": "<file or module involved>"
    }
  ],
  "summary": "<one sentence verdict>",
  "sprint": <sprint number integer>,
  "iteration": <iteration integer starting at 1>
}

Rules:
- passed=true ONLY when failed_tests == 0.
- passed=false when ANY test fails.
- Be specific about what failed and why.
- If no failures found, failures array is empty and summary is positive.

Output ONLY valid JSON — no markdown, no explanation outside it.
"""


class QAAgent(BaseAgent):
    """QA agent: validates an implementation and writes real pytest test files on disk via WriteQAReportAction."""

    artifact_name = "qa"

    def __init__(
        self,
        prompt_builder: QAPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        project_writer: ProjectWriter | None = None,
        project_reader: ProjectReader | None = None,
        file_validator: FileValidator | None = None,
        workspace_manager=None,
    ) -> None:
        self.project_writer = project_writer or ProjectWriter()
        self.project_reader = project_reader or ProjectReader()
        self.file_validator = file_validator or FileValidator()
        self._prompt_builder = prompt_builder or QAPromptBuilder(self.project_reader)
        self._workspace_manager = workspace_manager
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteQAReportAction."""
        return WriteQAReportAction(
            prompt_builder=self._prompt_builder,
            project_writer=self.project_writer,
            project_reader=self.project_reader,
            file_validator=self.file_validator,
        )

    def run_sprint_qa(
        self,
        project_id: str,
        sprint_number: int,
        file_plan: dict,
        architecture: dict,
        user_stories: dict,
        iteration: int = 1,
    ) -> dict:
        """Run QA for a single sprint and return structured test results.

        Builds a prompt from inputs, calls LLM for structured JSON test results,
        writes result to ArtifactStore(scope="sprint_{N}", name="qa_findings"),
        and returns the dict with safe defaults applied.

        Parameters
        ----------
        project_id:
            Project identifier.
        sprint_number:
            Sprint number (1-indexed).
        file_plan:
            Dictionary describing files planned for this sprint.
        architecture:
            Dictionary describing the architecture/design.
        user_stories:
            Dictionary with user stories and acceptance criteria.
        iteration:
            Current iteration of QA (used for feedback loops).

        Returns
        -------
        dict
            Structured test results: ``{"passed": bool, "total_tests": int, ...}``.
        """
        # Build prompt from inputs.
        prompt_parts = [
            "=== SPRINT QA TEST REPORT ===\n",
            f"Sprint: {sprint_number}",
            f"Iteration: {iteration}\n",
            f"FILE PLAN:\n{json.dumps(file_plan, indent=2)}\n",
            f"ARCHITECTURE:\n{json.dumps(architecture, indent=2)}\n",
            f"USER STORIES:\n{json.dumps(user_stories, indent=2)}\n",
            "Test the above and produce a structured test report as JSON.",
        ]
        prompt = "\n".join(prompt_parts)

        # Call LLM.
        response = self.llm_manager.generate_text(
            prompt,
            system_prompt=_SPRINT_QA_SYSTEM_PROMPT,
            stage="QA",
            agent="QAAgent",
        )

        # Extract and sanitize structured output.
        try:
            structured = json.loads(response.content) if response.content else {}
        except json.JSONDecodeError:
            logger.warning(
                "[QAAgent.run_sprint_qa] failed to parse LLM JSON response: %s",
                response.content[:200],
            )
            structured = {}

        # Apply safe defaults.
        structured.setdefault("passed", False)
        structured.setdefault("total_tests", 0)
        structured.setdefault("failed_tests", 0)
        structured.setdefault("failures", [])
        structured.setdefault("summary", "No test results")
        structured["sprint"] = sprint_number
        structured["iteration"] = iteration

        # Persist to sprint-scoped ArtifactStore when workspace_manager is wired.
        if self._workspace_manager is not None:
            try:
                store = self._workspace_manager.get_artifact_store(project_id)
                store.write(
                    scope=f"sprint_{sprint_number}",
                    name="qa_findings",
                    data={
                        "content": response.content,
                        "structured": structured,
                        "stage": "QA",
                        "written_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "[QAAgent.run_sprint_qa] non-fatal ArtifactStore write failure: %s", exc
                )

        return structured
