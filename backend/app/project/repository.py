from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

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
        data["current_stage"] = data["current_stage"]
        return Project(**data)
