from dataclasses import dataclass

from ..models.stage_artifact import StageArtifact


@dataclass(slots=True)
class ReviewRequest:
    artifact: StageArtifact
