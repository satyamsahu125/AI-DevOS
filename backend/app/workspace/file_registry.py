from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REGISTRY_FILENAME = "file_registry.json"


class FileRegistry:
    """Tracks which project files have been written, per project per sprint.

    Stored as artifacts/file_registry.json inside each project's workspace.
    Consulted by FileStructurePlanner (via its prompt) and WriteProjectFilesAction
    to decide whether to "create" or "update" a file.

    Design:
      - Keyed by file path (forward-slash, area-prefixed, e.g. "backend/models/user.py")
      - Each entry records which sprint wrote the file and the last update sprint
      - FileStructurePlanner reads this via context to know which files exist
      - No LLM calls — pure file-based bookkeeping

    Error contract: all methods catch exceptions and log warnings. A missing or
    corrupt registry is treated as empty (all files → "create").
    """

    def __init__(self, workspace_manager: Any = None) -> None:
        self._workspace = workspace_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, project_id: str, file_path: str) -> dict | None:
        """Return the registry entry for file_path, or None if not registered."""
        registry = self._load(project_id)
        return registry.get(self._normalize(file_path))

    def exists(self, project_id: str, file_path: str) -> bool:
        """Return True if file_path has been registered for project_id."""
        return self.get(project_id, file_path) is not None

    def record(self, project_id: str, file_path: str, sprint_number: int) -> None:
        """Record that file_path was written during sprint_number.

        On first write: sets created_sprint and last_updated_sprint.
        On subsequent writes: updates last_updated_sprint only.
        """
        try:
            registry = self._load(project_id)
            key = self._normalize(file_path)
            if key in registry:
                registry[key]["last_updated_sprint"] = sprint_number
            else:
                registry[key] = {
                    "path": key,
                    "created_sprint": sprint_number,
                    "last_updated_sprint": sprint_number,
                }
            self._save(project_id, registry)
        except Exception as exc:
            logger.warning("file_registry.record: failed for %s/%s sprint=%d: %s", project_id, file_path, sprint_number, exc)

    def record_many(self, project_id: str, file_paths: list[str], sprint_number: int) -> None:
        """Batch version of record() — more efficient for writing many files at once."""
        try:
            registry = self._load(project_id)
            for file_path in file_paths:
                key = self._normalize(file_path)
                if key in registry:
                    registry[key]["last_updated_sprint"] = sprint_number
                else:
                    registry[key] = {
                        "path": key,
                        "created_sprint": sprint_number,
                        "last_updated_sprint": sprint_number,
                    }
            self._save(project_id, registry)
        except Exception as exc:
            logger.warning("file_registry.record_many: failed for %s sprint=%d: %s", project_id, sprint_number, exc)

    def list_all(self, project_id: str) -> list[dict]:
        """Return all registered file entries for project_id."""
        try:
            return list(self._load(project_id).values())
        except Exception as exc:
            logger.warning("file_registry.list_all: failed for %s: %s", project_id, exc)
            return []

    def to_prompt_summary(self, project_id: str) -> str:
        """Render the registry as a compact text list for FileStructurePlanner's prompt.

        Format:
          EXISTING FILES (from prior sprints — these should be 'update' not 'create'):
          - backend/models/user.py (created sprint 1, last updated sprint 1)
          - backend/api/routes.py (created sprint 1, last updated sprint 2)
        """
        entries = self.list_all(project_id)
        if not entries:
            return ""
        lines = ["EXISTING FILES (from prior sprints — use operation='update' or 'patch' for these):"]
        for entry in sorted(entries, key=lambda e: e.get("path", "")):
            path = entry.get("path", "")
            created = entry.get("created_sprint", "?")
            updated = entry.get("last_updated_sprint", "?")
            lines.append(f"  - {path} (created sprint {created}, last updated sprint {updated})")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _registry_path(self, project_id: str) -> Path | None:
        if not self._workspace:
            return None
        try:
            ws_path = self._workspace.get_workspace_path(project_id)
            return ws_path / "artifacts" / _REGISTRY_FILENAME
        except Exception:
            return None

    def _load(self, project_id: str) -> dict[str, Any]:
        path = self._registry_path(project_id)
        if path is None or not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("file_registry._load: corrupt registry for %s: %s", project_id, exc)
            return {}

    def _save(self, project_id: str, registry: dict) -> None:
        path = self._registry_path(project_id)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("file_registry._save: failed for %s: %s", project_id, exc)

    @staticmethod
    def _normalize(file_path: str) -> str:
        return file_path.replace("\\", "/").lstrip("/")
