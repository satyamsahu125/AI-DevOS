from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from ..shared.enums.artifact_status import ArtifactStatus
from ..shared.models.stage_artifact import StageArtifact


class ArtifactManager:
    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or Path(__file__).resolve().parent.parent / "artifacts"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def create_artifact(self, name: str, content: str) -> StageArtifact:
        return StageArtifact(
            artifact_id=str(uuid4()),
            name=name,
            content=content,
            status=ArtifactStatus.Generated,
        )

    def save_artifact(self, artifact: StageArtifact) -> StageArtifact:
        artifact.status = ArtifactStatus.Stored
        artifact.location = self.storage_dir / f"{artifact.name}.md"
        artifact.location.write_text(artifact.content, encoding="utf-8")
        return artifact
