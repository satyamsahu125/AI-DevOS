from __future__ import annotations

from ..agents.base_agent import BaseAgent
from ..agents.product_owner import ProductOwnerAgent
from .exceptions import AgentResolutionException


class AgentFactory:
    """Resolve the documented agent implementation for a workflow stage."""

    def create(self, stage_name: str) -> BaseAgent:
        if stage_name.lower() == "productowner":
            return ProductOwnerAgent()
        raise AgentResolutionException(f"Unsupported stage: {stage_name}")
