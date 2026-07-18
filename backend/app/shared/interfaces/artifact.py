from abc import ABC, abstractmethod

from ..models.stage_artifact import StageArtifact


class ArtifactInterface(ABC):
    @abstractmethod
    def save(self, artifact: StageArtifact) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self, id: str) -> StageArtifact:
        raise NotImplementedError

    @abstractmethod
    def latest(self, project_id: str) -> list[StageArtifact]:
        raise NotImplementedError
