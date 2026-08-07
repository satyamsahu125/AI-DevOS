from __future__ import annotations

import logging

from ..actions.base_action import BaseAction
from ..llm.manager import LLMManager
from ..prompt.domain_research_builder import DomainResearchPromptBuilder
from ..shared.schemas.domain_schema import DomainBrief
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DomainResearcherAgent(BaseAgent):
    """Researches the domain of a software request before Q&A begins.

    Runs BEFORE ClarificationAgent so the Q&A can ask domain-specific
    questions instead of generic ones.

    Input:  raw user request ("Build a food delivery app like Swiggy")
    Output: DomainBrief with standard modules, actors, smart questions,
            pitfalls, and regulatory concerns for this domain.
    """

    artifact_name = "domain_research"

    def __init__(
        self,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        self._prompt_builder = DomainResearchPromptBuilder()
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        # DomainResearcherAgent calls LLM directly via research() and does not
        # use primary_action.  Return a minimal concrete stub so BaseAgent.__init__
        # can assign self.primary_action without raising.
        from ..actions.base_action import ActionOutput

        class _NoOpAction(BaseAction):
            def run(self, context: object, llm: object) -> ActionOutput:  # type: ignore[override]
                return ActionOutput(content="", structured_content={})

        return _NoOpAction()

    def research(self, request: str) -> DomainBrief:
        """Analyze the request and return a structured DomainBrief.

        Gracefully degrades to an empty DomainBrief on any LLM/parse error
        so that a domain research failure never blocks the Q&A stage.
        """
        try:
            prompt = self._prompt_builder.build_research_prompt(request)
            response = self.llm_manager.generate_text(
                prompt=prompt,
                system_prompt=self._prompt_builder.system_prompt,
                stage="domain_research",
            )
            raw = getattr(response, "content", str(response))
            data = BaseAction.extract_json(raw)
            if data:
                return DomainBrief.model_validate(data)
            logger.warning("DomainResearcher: no JSON found in LLM response — using empty brief")
        except Exception as exc:
            logger.warning("DomainResearcher.research() failed (non-fatal): %s", exc)
        return DomainBrief(domain="unknown", complexity="medium")
