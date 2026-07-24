from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..shared.enums.stage import Stage
from ..shared.models.project import Project


class ProjectRepository:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[1] / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, project: Project) -> Project:
        path = self.root / f"{project.project_id}.json"
        payload = project.__dict__.copy()
        payload["created_at"] = project.created_at.isoformat()
        payload["current_stage"] = project.current_stage.value
        path.write_text(json.dumps(payload), encoding="utf-8")
        return project

    def load(self, project_id: str) -> Optional[Project]:
        path = self.root / f"{project_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["current_stage"] = Stage(data["current_stage"])
        data.setdefault("status", "active")
        return Project(**data)

    def exists(self, project_id: str) -> bool:
        return (self.root / f"{project_id}.json").exists()

    def delete(self, project_id: str) -> bool:
        """Delete project_id's saved record. Returns whether it existed."""
        path = self.root / f"{project_id}.json"
        if not path.exists():
            return False
        path.unlink()
        return True

    def list_projects(self) -> list[Project]:
        """Return every saved project, skipping any file that fails to parse (e.g. a legacy record predating a schema field)."""
        projects: list[Project] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                project = self.load(path.stem)
            except (KeyError, ValueError):
                continue
            if project is not None:
                projects.append(project)
        return projects
