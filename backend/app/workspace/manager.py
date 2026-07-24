from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .layout import WorkspaceLayout
from .repository import WorkspaceRepository


class WorkspaceManager:
    """Owns every project's on-disk workspace, keyed by project_id (not name).

    Each project gets exactly one directory: `temp-workspace/{project_id}/`,
    containing the documented backend/frontend/docs/artifacts/temp
    subdirectories plus a `project.json` tracking file that records
    current_stage/stages_completed/status as the workflow progresses --
    the durable source of truth GET /projects/{project_id} reads from.
    """

    def __init__(self, root: Path | None = None) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        self.root = root or backend_root / "temp-workspace"
        self.layout = WorkspaceLayout(self.root)
        self.repository = WorkspaceRepository(self.root)

    def create_workspace(self, project_id: str, name: str = "", description: str = "") -> Path:
        """Create (idempotently) the workspace directory tree for project_id and seed project.json."""
        workspace_root = self.repository.create() / project_id
        workspace_root.mkdir(parents=True, exist_ok=True)
        for directory in self.layout.directories():
            (workspace_root / directory.name).mkdir(parents=True, exist_ok=True)

        project_json_path = workspace_root / "project.json"
        if not project_json_path.exists():
            payload = {
                "project_id": project_id,
                "name": name,
                "description": description,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "stages_completed": [],
                "current_stage": None,
                "status": "active",
            }
            project_json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return workspace_root

    def delete_workspace(self, project_id: str) -> bool:
        """Delete project_id's entire workspace directory tree. Returns whether it existed."""
        workspace_root = self.get_workspace_path(project_id)
        if not workspace_root.exists():
            return False
        shutil.rmtree(workspace_root)
        return True

    def get_workspace_path(self, project_id: str) -> Path:
        """Return the workspace directory for project_id (may not exist yet)."""
        return self.root / project_id

    def get_artifact_path(self, project_id: str, stage: str) -> Path:
        """Return the canonical markdown artifact path for project_id/stage."""
        return self.get_workspace_path(project_id) / "artifacts" / f"{stage}.md"

    def get_docs_path(self, project_id: str) -> Path:
        """Return the docs directory for project_id."""
        return self.get_workspace_path(project_id) / "docs"

    def load_project_json(self, project_id: str) -> dict | None:
        """Return the parsed project.json for project_id, or None if the workspace has none."""
        path = self.get_workspace_path(project_id) / "project.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def update_project_json(self, project_id: str, updates: dict) -> None:
        """Merge updates into project.json, creating the file if the workspace predates it."""
        path = self.get_workspace_path(project_id) / "project.json"
        data = self.load_project_json(project_id) or {"project_id": project_id}
        data.update(updates)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
