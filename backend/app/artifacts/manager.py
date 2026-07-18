from __future__ import annotations

from pathlib import Path


class ArtifactManager:
    """Stores generated artifacts on disk."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        self.storage_dir = storage_dir or Path(__file__).resolve().parent.parent / "artifacts"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_artifact(self, name: str, content: str) -> Path:
        path = self.storage_dir / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        return path
