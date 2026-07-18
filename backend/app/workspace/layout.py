from pathlib import Path


class WorkspaceLayout:
    def __init__(self, root: Path) -> None:
        self.root = root

    def directories(self) -> list[Path]:
        return [
            self.root / "backend",
            self.root / "frontend",
            self.root / "docs",
            self.root / "artifacts",
            self.root / "temp",
        ]
