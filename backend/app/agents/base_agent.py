from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..actions.base_action import BaseAction
from ..llm.manager import LLMManager
from ..shared.models.stage_artifact import StageArtifact

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Base contract shared by every stage agent.

    Every agent has a primary_action (see actions/base_action.py) that does
    the actual LLM-backed work and returns an ActionOutput; execute() just
    delegates to it and wraps the result as a StageArtifact. Agents never
    call an LLM provider directly -- every LLM call is routed through the
    LLMManager injected at construction time.
    """

    artifact_name: str = ""

    def __init__(self, llm_manager: LLMManager | None = None, primary_action: BaseAction | None = None) -> None:
        """Store the LLMManager this agent uses, and build (or accept) its primary_action."""
        self.llm_manager = llm_manager or LLMManager()
        self.primary_action = primary_action or self._build_default_action()
        logger.debug("%s initialized: action=%s", type(self).__name__, self.primary_action.name)

    @abstractmethod
    def _build_default_action(self) -> BaseAction:
        """Construct this agent's default primary_action when none is injected at construction time."""
        raise NotImplementedError

    def execute(self, context: object) -> StageArtifact:
        """Run primary_action against context and wrap its ActionOutput as a StageArtifact."""
        logger.info("%s executing: action=%s", type(self).__name__, self.primary_action.name)
        output = self.primary_action.run(context, self.llm_manager)
        return StageArtifact(
            artifact_id="",
            name=self.artifact_name,
            content=output.content,
            status="Generated",
            schema_type=self.primary_action.name,
            structured_content=output.structured,
        )
