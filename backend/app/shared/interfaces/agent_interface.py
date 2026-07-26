from abc import ABC, abstractmethod

from ..models.stage_artifact import StageArtifact


class AgentInterface(ABC):
    """Abstract interface for all stage agents.

    NOTE: No concrete agent currently inherits from this class — agents inherit
    from BaseAgent (agents/base_agent.py) which does not extend AgentInterface.
    AgentInterface is retained because kernel/container.py uses it as the return
    type annotation of the ``registry`` property. Once BaseAgent or all concrete
    agents are made to implement AgentInterface, this will enforce the contract.
    """

    @abstractmethod
    def execute(self, context: object) -> StageArtifact:
        raise NotImplementedError
