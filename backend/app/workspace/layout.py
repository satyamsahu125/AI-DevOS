from pathlib import Path


class WorkspaceLayout:
    """Defines the canonical directory structure for a single project workspace.

    Static layout created on workspace init::

        {root}/
            backend/
            frontend/
            docs/
            artifacts/
                project/   ← discovery-phase artifacts (always created)
                release/   ← post-sprint release artifacts (always created)
            temp/

    Sprint artifact directories (``artifacts/sprint_{N}/``) are created
    dynamically by :meth:`WorkspaceManager.create_sprint_folder` and are
    therefore **not** listed here.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def directories(self) -> list[Path]:
        """Return every directory that must exist in a fresh workspace."""
        return [
            self.root / "backend",
            self.root / "frontend",
            self.root / "docs",
            self.root / "artifacts",
            self.root / "artifacts" / "project",
            self.root / "artifacts" / "release",
            self.root / "temp",
        ]

    def sprint_artifact_dir(self, sprint_number: int) -> Path:
        """Return the expected path for sprint *sprint_number*'s artifact directory."""
        return self.root / "artifacts" / f"sprint_{sprint_number}"
