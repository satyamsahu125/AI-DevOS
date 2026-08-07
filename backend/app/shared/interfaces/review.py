from abc import ABC, abstractmethod

from ..models.review import Review
from ..models.stage_artifact import StageArtifact


class ReviewInterface(ABC):
    @abstractmethod
    def review(self, artifact: StageArtifact) -> Review:
        raise NotImplementedError
