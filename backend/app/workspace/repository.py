from pathlib import Path


class WorkspaceRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def exists(self) -> bool:
        return self.root.exists()

    def create(self) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root
