from pathlib import Path

from .layout import WorkspaceLayout
from .repository import WorkspaceRepository


class WorkspaceManager:
    def __init__(self, root: Path | None = None) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        self.root = root or backend_root / "temp-workspace"
        self.layout = WorkspaceLayout(self.root)
        self.repository = WorkspaceRepository(self.root)

    def create_workspace(self, project_name: str) -> Path:
        workspace_root = self.repository.create() / project_name.replace(" ", "-").lower()
        workspace_root.mkdir(parents=True, exist_ok=True)
        for directory in self.layout.directories():
            (workspace_root / directory.name).mkdir(parents=True, exist_ok=True)
        return workspace_root
