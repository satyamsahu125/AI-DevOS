from abc import ABC, abstractmethod

from ..models.stage_artifact import StageArtifact


class AgentInterface(ABC):
    @abstractmethod
    def execute(self, context: object) -> StageArtifact:
        raise NotImplementedError
