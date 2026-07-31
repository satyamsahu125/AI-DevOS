from __future__ import annotations

from typing import Any

from ..prompt.clarification_builder import ClarificationPromptBuilder
from ..shared.schemas.clarification_schema import ClarificationArtifact
from ..shared.schemas.qa_session_schema import QuestionSet
from .base_action import LLMAction


class GenerateQuestionsAction(LLMAction):
    """Phase A: Analyze request and generate targeted questions.

    Does NOT answer the questions — waits for real user input.
    """

    name = "GenerateQuestions"
    description = "Analyze request and generate questions for the user."
    schema_model = QuestionSet
    system_prompt = (
        "You are a Requirements Clarification Specialist. "
        "Analyze the request and return ONLY a JSON object with key 'questions' "
        "containing a list of Question objects (index, question, category, priority, options, allows_custom, skippable)."
    )

    def __init__(self, prompt_builder: ClarificationPromptBuilder | None = None) -> None:
        super().__init__(prompt_builder or ClarificationPromptBuilder())

    def run_generate(self, request: str, llm_manager: Any, domain_brief: dict | None = None) -> QuestionSet:
        builder = self.prompt_builder
        if hasattr(builder, "build_generate_prompt"):
            import inspect
            sig = inspect.signature(builder.build_generate_prompt)
            if "domain_brief" in sig.parameters:
                prompt = builder.build_generate_prompt(request, domain_brief=domain_brief)
            else:
                prompt = builder.build_generate_prompt(request)
        else:
            prompt = f"Generate questions for request: {request}"
        response = llm_manager.generate_text(prompt=prompt, system_prompt=self.system_prompt)
        content = response.content if hasattr(response, "content") else str(response)
        parsed = self._parse_structured(content)
        if parsed:
            return QuestionSet.model_validate(parsed)
        return QuestionSet(questions=[])


class ProcessAnswersAction(LLMAction):
    """Phase B: Combine request + user answers into enriched requirement.

    Runs after user has answered all questions.
    """

    name = "ProcessAnswers"
    description = "Process user Q&A answers into a complete ClarificationArtifact."
    schema_model = ClarificationArtifact
    system_prompt = (
        "You are a Requirements Clarification Specialist. "
        "Combine the original request and user answers into a single JSON object matching ClarificationArtifact."
    )

    def __init__(self, prompt_builder: ClarificationPromptBuilder | None = None) -> None:
        super().__init__(prompt_builder or ClarificationPromptBuilder())

    def run_process(self, original_request: str, qa_session: dict[str, Any], llm_manager: Any) -> ClarificationArtifact:
        builder = self.prompt_builder
        prompt = (
            builder.build_process_prompt(original_request, qa_session)
            if hasattr(builder, "build_process_prompt")
            else f"Process answers for request: {original_request}\nAnswers: {qa_session}"
        )
        try:
            response = llm_manager.generate_text(prompt=prompt, system_prompt=self.system_prompt)
            content = response.content if hasattr(response, "content") else str(response)
            parsed = self._parse_structured(content)
            if parsed:
                return ClarificationArtifact.model_validate(parsed)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("ProcessAnswersAction failed: %s", exc)
        return ClarificationArtifact(original_request=original_request)


class ClarifyRequirementsAction(LLMAction):
    """Backward-compatible action wrapping ClarificationArtifact production."""

    name = "ClarifyRequirements"
    description = "Clarify ambiguous user requirements, ask questions, make assumptions, and enrich requirements."
    schema_model = ClarificationArtifact
    system_prompt = (
        "You are a Requirements Clarification Specialist. "
        "Respond with ONLY a single JSON object matching ClarificationArtifact schema."
    )

    def __init__(self, prompt_builder: ClarificationPromptBuilder | None = None) -> None:
        super().__init__(prompt_builder or ClarificationPromptBuilder())
