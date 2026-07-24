from fastapi import APIRouter

from ..agents.base_agent import BaseAgent
from ..agents.factory import AgentFactory

router = APIRouter()


@router.get("/agents")
def list_agents() -> list[dict]:
    """Report every registered agent's real/stub status, derived by checking whether execute()
    is overridden (a stub bypasses BaseAgent.execute()'s LLM-backed delegation entirely)."""
    factory = AgentFactory()
    result = []
    for stage_key, implementation in factory.registry.agents.items():
        agent_cls = implementation if isinstance(implementation, type) else type(implementation)
        instance = implementation() if isinstance(implementation, type) else implementation
        llm_backed = agent_cls.execute is BaseAgent.execute
        action = instance.primary_action
        prompt_builder = getattr(action, "prompt_builder", None)
        result.append({
            "agent": agent_cls.__name__,
            "stage": stage_key,
            "status": "real" if llm_backed else "stub",
            "llm_backed": llm_backed,
            "prompt_builder": type(prompt_builder).__name__ if prompt_builder is not None else "NONE",
            "output_schema": action.schema_model.__name__ if getattr(action, "schema_model", None) else "NONE",
        })
    return result
