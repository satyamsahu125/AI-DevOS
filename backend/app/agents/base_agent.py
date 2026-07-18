from __future__ import annotations

from abc import ABC, abstractmethod

from ..shared.models.stage_artifact import StageArtifact


class BaseAgent(ABC):
    """Minimal agent contract used by the documented runtime."""

    @abstractmethod
    def execute(self, context: object) -> StageArtifact:
        raise NotImplementedError
