from __future__ import annotations

from typing import Any

from ..artifact.manager import ArtifactManager
from ..config.manager import ConfigurationManager
from ..llm.manager import LLMManager


class DependencyProvider:
    """Provides the default dependencies required by runtime agents."""

    def __init__(self, config_manager: ConfigurationManager | None = None, llm_manager: LLMManager | None = None, artifact_manager: ArtifactManager | None = None) -> None:
        self.config_manager = config_manager or ConfigurationManager()
        self.llm_manager = llm_manager or LLMManager(config_manager=self.config_manager)
        self.artifact_manager = artifact_manager or ArtifactManager()

    def provide(self) -> dict[str, Any]:
        return {
            "configuration": self.config_manager,
            "llm_manager": self.llm_manager,
            "artifact_manager": self.artifact_manager,
            "logger": None,
        }
