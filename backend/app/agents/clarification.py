from __future__ import annotations

from typing import Any

from ..actions.base_action import BaseAction
from ..actions.clarify_requirements import ClarifyRequirementsAction, GenerateQuestionsAction, ProcessAnswersAction
from ..llm.manager import LLMManager
from ..shared.schemas.clarification_schema import ClarificationArtifact
from ..shared.schemas.qa_session_schema import QuestionSet
from .base_agent import BaseAgent


class ClarificationAgent(BaseAgent):
    """Requirements Clarification agent (runs before ProductOwner)."""

    artifact_name = "clarification-report"

    def __init__(self, llm_manager: LLMManager | None = None, primary_action: BaseAction | None = None) -> None:
        """Store LLMManager and build default action."""
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)
        self.generate_action = GenerateQuestionsAction()
        self.process_action = ProcessAnswersAction()

    def _build_default_action(self) -> BaseAction:
        return ClarifyRequirementsAction()

    def generate_questions(self, request: str, domain_brief: dict | None = None) -> QuestionSet:
        """Phase A: Analyze request and generate up to 7 targeted questions.

        When ``domain_brief`` is provided (from DomainResearcherAgent), the prompt
        is enriched with domain-specific smart questions and a list of obvious
        questions to skip, so the Q&A is domain-aware from the start.
        """
        return self.generate_action.run_generate(request, self.llm_manager, domain_brief=domain_brief)

    def process_answers(self, original_request: str, qa_session: dict[str, Any]) -> ClarificationArtifact:
        """Phase B: Combine request + user answers into ClarificationArtifact."""
        return self.process_action.run_process(original_request, qa_session, self.llm_manager)
