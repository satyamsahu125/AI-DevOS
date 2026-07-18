from __future__ import annotations

from typing import Sequence

from .agent_factory import AgentFactory
from .exceptions import AgentResolutionException


class MultiAgentOrchestrator:
    """Simple orchestrator for the documented multi-agent execution contract."""

    def __init__(self, agent_factory: AgentFactory | None = None) -> None:
        self.agent_factory = agent_factory or AgentFactory()

    def resolve_next_agent(self, stage_name: str) -> object:
        try:
            return self.agent_factory.create(stage_name)
        except AgentResolutionException as exc:
            raise RuntimeError(str(exc)) from exc

    def resolve_order(self, stages: Sequence[str]) -> list[str]:
        return list(stages)
