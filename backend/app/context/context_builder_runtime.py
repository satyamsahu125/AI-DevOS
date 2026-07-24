from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..artifact.manager import ArtifactManager
from ..project.manager import ProjectManager
from ..shared.models.stage_artifact import StageArtifact
from .context import AgentContext


@dataclass(slots=True)
class ContextBuilderRuntime:
    """Builds an AgentContext from runtime sources."""

    project_manager: ProjectManager | None = None
    artifact_manager: ArtifactManager | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def build(self, project_name: str = "", requirements: str = "", architecture: str = "") -> AgentContext:
        return AgentContext(
            project_name=project_name or "demo",
            requirements=requirements or "requirements",
            architecture=architecture or "architecture",
            metadata=self.metadata,
        )
