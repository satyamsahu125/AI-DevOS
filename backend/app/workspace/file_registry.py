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
        entry = registry.get(self._normalize(file_path))
        if entry is None:
            return None
        return dict(entry)

    def exists(self, project_id: str, file_path: str) -> bool:
        """Return True if file_path has been registered for project_id."""
        return self.get(project_id, file_path) is not None

    def register(
        self,
        project_id: str,
        file_path: str,
        sprint_number: int,
        area: str = "",
        operation: str = "create",
    ) -> None:
        """Register that file_path was written during sprint_number.

        On first write: sets area, created_sprint, last_updated_sprint, operation,
        requirement_version_id, and sprint_history.
        On subsequent writes: updates last_updated_sprint, operation,
        requirement_version_id, and appends to sprint_history (preserving created_sprint).
        """
        try:
            registry = self._load(project_id)
            key = self._normalize(file_path)
            req_version_id = self._get_current_requirement_version_id(project_id)
            resolved_area = area.strip().lower() if area else self._infer_area(key)

            if key in registry:
                entry = registry[key]
                entry["last_updated_sprint"] = sprint_number
                entry["operation"] = operation
                if resolved_area:
                    entry["area"] = resolved_area
                entry["requirement_version_id"] = req_version_id
                sprints = entry.get("sprint_history", [])
                if sprint_number not in sprints:
                    sprints.append(sprint_number)
                entry["sprint_history"] = sprints
            else:
                registry[key] = {
                    "path": key,
                    "area": resolved_area,
                    "created_sprint": sprint_number,
                    "last_updated_sprint": sprint_number,
                    "operation": operation,
                    "requirement_version_id": req_version_id,
                    "sprint_history": [sprint_number],
                }
            self._save(project_id, registry)
        except Exception as exc:
            logger.warning("file_registry.register: failed for %s/%s sprint=%d: %s", project_id, file_path, sprint_number, exc)

    def record(
        self,
        project_id: str,
        file_path: str,
        sprint_number: int,
        area: str = "",
        operation: str = "create",
    ) -> None:
        """Backward compatible delegate for register()."""
        self.register(project_id, file_path, sprint_number, area=area, operation=operation)

    def record_many(
        self,
        project_id: str,
        file_paths: list[str],
        sprint_number: int,
        area: str = "",
        operation: str = "create",
    ) -> None:
        """Batch version of register() — more efficient for writing many files at once."""
        try:
            registry = self._load(project_id)
            req_version_id = self._get_current_requirement_version_id(project_id)
            for file_path in file_paths:
                key = self._normalize(file_path)
                resolved_area = area.strip().lower() if area else self._infer_area(key)
                if key in registry:
                    entry = registry[key]
                    entry["last_updated_sprint"] = sprint_number
                    entry["operation"] = operation
                    if resolved_area:
                        entry["area"] = resolved_area
                    entry["requirement_version_id"] = req_version_id
                    sprints = entry.get("sprint_history", [])
                    if sprint_number not in sprints:
                        sprints.append(sprint_number)
                    entry["sprint_history"] = sprints
                else:
                    registry[key] = {
                        "path": key,
                        "area": resolved_area,
                        "created_sprint": sprint_number,
                        "last_updated_sprint": sprint_number,
                        "operation": operation,
                        "requirement_version_id": req_version_id,
                        "sprint_history": [sprint_number],
                    }
            self._save(project_id, registry)
        except Exception as exc:
            logger.warning("file_registry.record_many: failed for %s sprint=%d: %s", project_id, sprint_number, exc)

    def list_all(self, project_id: str) -> list[dict]:
        """Return all registered file entries for project_id."""
        try:
            return [dict(e) for e in self._load(project_id).values()]
        except Exception as exc:
            logger.warning("file_registry.list_all: failed for %s: %s", project_id, exc)
            return []

    def get_existing(self, project_id: str, area: str) -> list[dict]:
        """Return existing files registered for project_id and area.

        Requirements:
          - Project isolation
          - Area filtering (exact or inferred)
          - Deterministic ordering by path
          - No mutation of registry state
        """
        try:
            target_area = area.strip().lower()
            registry = self._load(project_id)
            matched = []
            for key, entry in sorted(registry.items(), key=lambda item: item[0]):
                entry_area = (entry.get("area") or "").lower() or self._infer_area(key)
                if entry_area == target_area:
                    matched.append(dict(entry))
            return matched
        except Exception as exc:
            logger.warning("file_registry.get_existing: failed for %s/%s: %s", project_id, area, exc)
            return []

    def get_sprint_files(self, project_id: str, sprint: int) -> list[dict]:
        """Return files associated with project_id and sprint.

        Requirements:
          - Project isolation
          - Exact sprint filtering (created or updated in sprint)
          - Deterministic result ordering by path
          - Includes enough information to determine create/update/patch status
          - No mutation of registry state
        """
        try:
            registry = self._load(project_id)
            matched = []
            for key, entry in sorted(registry.items(), key=lambda item: item[0]):
                sprints = entry.get("sprint_history") or []
                if sprint in sprints or entry.get("created_sprint") == sprint or entry.get("last_updated_sprint") == sprint:
                    matched.append(dict(entry))
            return matched
        except Exception as exc:
            logger.warning("file_registry.get_sprint_files: failed for %s/sprint %d: %s", project_id, sprint, exc)
            return []

    def was_written_in_sprint(self, project_id: str, area: str, path: str, sprint: int) -> bool:
        """Return True only when the file was registered/written for exact project, area, normalized path, and sprint."""
        try:
            registry = self._load(project_id)
            if not registry:
                return False

            norm_path = self._normalize(path)
            target_area = area.strip().lower()

            for key, entry in registry.items():
                e_path = self._normalize(entry.get("path", key))
                e_area = (entry.get("area") or "").lower() or self._infer_area(e_path)

                # Path match (exact normalized path, or path prefixed/unprefixed by area)
                path_matches = (
                    e_path == norm_path
                    or e_path == self._normalize(f"{target_area}/{norm_path}")
                    or norm_path == self._normalize(f"{target_area}/{e_path}")
                )
                if not path_matches:
                    continue

                # Area match
                area_matches = (e_area == target_area) or (not e_area and e_path.startswith(f"{target_area}/"))
                if not area_matches:
                    continue

                # Sprint match
                sprints = entry.get("sprint_history") or []
                sprint_matches = (
                    sprint in sprints
                    or entry.get("created_sprint") == sprint
                    or entry.get("last_updated_sprint") == sprint
                )
                if sprint_matches:
                    return True

            return False
        except Exception as exc:
            logger.warning(
                "file_registry.was_written_in_sprint: failed for %s/%s/%s sprint %d: %s",
                project_id, area, path, sprint, exc
            )
            return False

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

    def _get_current_requirement_version_id(self, project_id: str) -> str | None:
        """Return current_requirement_version_id from project.json, or None.

        Non-fatal: any failure returns None so file registration always
        succeeds even when versioning is not yet active.
        """
        if not self._workspace:
            return None
        try:
            pj = self._workspace.load_project_json(project_id) or {}
            return pj.get("current_requirement_version_id") or None
        except Exception as exc:
            logger.debug("file_registry: could not read requirement version (non-fatal): %s", exc)
            return None

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

    @staticmethod
    def _infer_area(file_path: str) -> str:
        norm = file_path.replace("\\", "/").lstrip("/")
        parts = norm.split("/")
        if parts and parts[0] in ("backend", "frontend", "mobile"):
            return parts[0]
        return ""

