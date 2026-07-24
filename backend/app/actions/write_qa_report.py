from __future__ import annotations

from ..prompt.qa_builder import QAPromptBuilder
from ..shared.schemas.qa_schema import QAArtifact
from .base_action import LLMAction


class WriteQAReportAction(LLMAction):
    """QA's action: produces a structured QAArtifact."""

    name = "WriteQAReport"
    description = "Validate the implementation and report test cases, coverage, and bugs found."
    schema_model = QAArtifact
    system_prompt = (
        "You are a QA Engineer validating an implementation. "
        "Respond with ONLY a single JSON object (no prose outside it) with these keys: "
        "test_cases (list of objects with name/steps/expected/actual/status), "
        "coverage_percent (number), bugs_found (list of objects with id/severity/description/file/line), "
        "regression_tests (list of strings)."
    )

    def __init__(self, prompt_builder: QAPromptBuilder | None = None) -> None:
        """Wire the QA prompt builder this action uses."""
        super().__init__(prompt_builder or QAPromptBuilder())
