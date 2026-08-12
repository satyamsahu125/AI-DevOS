from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..shared.enums.artifact_status import ArtifactStatus
from ..shared.enums.stage import Stage
from ..shared.models.stage_artifact import StageArtifact
from ..workspace.manager import WorkspaceManager

# Phase 6 MIGRATE: anchored default — parents[2] from backend/app/artifact/ = backend/.
# Previous default "memory/memory.db" was relative and pointed to the wrong location.
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_DEFAULT_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", str(_DATA_DIR / "memory.sqlite")))


class ArtifactManager:
    """Persists stage artifacts, isolated per project_id.

    Every save_artifact() call writes an attempt-numbered JSON file (full
    history, never overwritten) plus refreshes the canonical `{stage}.md`/
    `{stage}.json` pair representing the latest attempt, and records a row
    in the shared `artifacts` SQLite table (same memory.db SafetyPolicy and
    CostTracker use) so approval status and history can be queried without
    re-reading every file on disk.
    """

    def __init__(
        self,
        storage_dir: Path | None = None,
        workspace_manager: WorkspaceManager | None = None,
        db_path: Path | None = None,
    ) -> None:
        """Wire the legacy flat storage_dir (used only by create_artifact), the
        WorkspaceManager used to resolve per-project artifact paths, and the
        SQLite database backing the artifacts audit table."""
        self.storage_dir = storage_dir or Path(__file__).resolve().parent.parent / "artifacts"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._ensure_schema()

    def close(self) -> None:
        """Close SQLite database connection to release file lock."""
        if hasattr(self, "_conn") and self._conn:
            try:
                self._conn.close()
            except Exception:
                pass

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                file_path TEXT NOT NULL,
                json_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.commit()

    def create_artifact(self, name: str, content: str) -> StageArtifact:
        """Construct a bare, unsaved StageArtifact (legacy helper, no project scoping)."""
        return StageArtifact(
            artifact_id=str(uuid4()),
            name=name,
            content=content,
            status=ArtifactStatus.Generated,
        )

    def save_artifact(
        self,
        project_id: str,
        stage: Stage,
        content: str,
        structured_content: dict | None = None,
        *,
        attempt: int = 1,
        artifact_id: str = "",
        schema_type: str = "",
        safety_flags: list[str] | None = None,
    ) -> StageArtifact:
        """Write this attempt's artifact for project_id/stage, and refresh the canonical latest-attempt files."""
        structured_content = structured_content or {}
        safety_flags = list(safety_flags or [])
        now = datetime.now(timezone.utc)

        # Non-fatal: read current requirement version from project.json
        requirement_version_id: str | None = None
        try:
            pj = self.workspace_manager.load_project_json(project_id) or {}
            requirement_version_id = pj.get("current_requirement_version_id") or None
        except Exception:
            pass

        artifacts_dir = self.workspace_manager.get_workspace_path(project_id) / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        md_path = artifacts_dir / f"{stage.value}.md"
        json_path = artifacts_dir / f"{stage.value}.json"
        attempt_json_path = artifacts_dir / f"{stage.value}.attempt-{attempt}.json"

        md_body = (
            f"# {stage.value} Artifact\n"
            f"# Project: {project_id}\n"
            f"# Generated: {now.isoformat()}\n"
            f"# Attempt: {attempt}\n\n"
            f"## Raw Output\n{content}\n\n"
            f"## Structured Data\n```json\n{json.dumps(structured_content, indent=2)}\n```\n"
        )
        md_path.write_text(md_body, encoding="utf-8")

        json_body = {
            "project_id": project_id,
            "stage": stage.value,
            "generated_at": now.isoformat(),
            "attempt": attempt,
            "content": content,
            "structured": structured_content,
            "requirement_version_id": requirement_version_id,
        }
        json_text = json.dumps(json_body, indent=2)
        json_path.write_text(json_text, encoding="utf-8")
        attempt_json_path.write_text(json_text, encoding="utf-8")

        self._conn.execute(
            "INSERT INTO artifacts (project_id, stage, file_path, json_path, created_at, attempt, approved) "
            "VALUES (?, ?, ?, ?, ?, ?, 0)",
            (project_id, stage.value, str(md_path), str(json_path), now.isoformat(), attempt),
        )
        self._conn.commit()

        return StageArtifact(
            artifact_id=artifact_id or str(uuid4()),
            name=stage.value,
            content=content,
            status=ArtifactStatus.Stored,
            location=md_path,
            schema_type=schema_type,
            structured_content=structured_content,
            safety_flags=safety_flags,
            project_id=project_id,
            attempt=attempt,
            requirement_version_id=requirement_version_id,
        )

    def is_approved(self, project_id: str, stage: Stage, attempt: int) -> bool:
        """Return whether the given attempt is marked approved for project_id/stage."""
        row = self._conn.execute(
            "SELECT approved FROM artifacts WHERE project_id = ? AND stage = ? AND attempt = ?",
            (project_id, stage.value, attempt),
        ).fetchone()
        return bool(row and row[0])

    def delete_project_artifacts(self, project_id: str) -> int:
        """Delete every artifacts-table row for project_id. Returns how many rows were deleted."""
        cursor = self._conn.execute("DELETE FROM artifacts WHERE project_id = ?", (project_id,))
        self._conn.commit()
        return cursor.rowcount if cursor.rowcount is not None and cursor.rowcount > 0 else 0

    def mark_approved(self, project_id: str, stage: Stage, attempt: int) -> None:
        """Mark the given attempt as the approved artifact for project_id/stage."""
        self._conn.execute(
            "UPDATE artifacts SET approved = 1 WHERE project_id = ? AND stage = ? AND attempt = ?",
            (project_id, stage.value, attempt),
        )
        self._conn.commit()

    def get_artifact(self, project_id: str, stage: Stage) -> StageArtifact | None:
        """Return the latest saved artifact for project_id/stage, or None if it has never been saved."""
        json_path = self.workspace_manager.get_workspace_path(project_id) / "artifacts" / f"{stage.value}.json"
        if not json_path.exists():
            return None
        data = json.loads(json_path.read_text(encoding="utf-8"))
        row = self._conn.execute(
            "SELECT attempt, approved FROM artifacts WHERE project_id = ? AND stage = ? ORDER BY id DESC LIMIT 1",
            (project_id, stage.value),
        ).fetchone()
        attempt = row[0] if row else data.get("attempt", 1)
        return StageArtifact(
            artifact_id="",
            name=stage.value,
            content=data.get("content", ""),
            status=ArtifactStatus.Stored,
            location=self.workspace_manager.get_workspace_path(project_id) / "artifacts" / f"{stage.value}.md",
            structured_content=data.get("structured", {}),
            project_id=project_id,
            attempt=attempt,
            requirement_version_id=data.get("requirement_version_id"),
        )

    def list_artifacts(self, project_id: str) -> list[StageArtifact]:
        """Return every approved artifact for project_id, one entry per stage (its latest approved attempt)."""
        rows = self._conn.execute(
            """
            SELECT stage, file_path, json_path, attempt FROM artifacts
            WHERE project_id = ? AND approved = 1 AND id IN (
                SELECT MAX(id) FROM artifacts WHERE project_id = ? AND approved = 1 GROUP BY stage
            ) ORDER BY id ASC
            """,
            (project_id, project_id),
        ).fetchall()
        return [self._row_to_artifact(project_id, stage_value, file_path, json_path, attempt) for stage_value, file_path, json_path, attempt in rows]

    def get_artifact_history(self, project_id: str, stage: Stage) -> list[StageArtifact]:
        """Return every attempt (approved or not) ever saved for project_id/stage, oldest first."""
        rows = self._conn.execute(
            "SELECT stage, file_path, json_path, attempt FROM artifacts "
            "WHERE project_id = ? AND stage = ? ORDER BY attempt ASC",
            (project_id, stage.value),
        ).fetchall()
        return [self._row_to_artifact(project_id, stage_value, file_path, json_path, attempt) for stage_value, file_path, json_path, attempt in rows]

    def _row_to_artifact(self, project_id: str, stage_value: str, file_path: str, json_path: str, attempt: int) -> StageArtifact:
        content, structured, requirement_version_id = "", {}, None
        path = Path(json_path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            content = data.get("content", "")
            structured = data.get("structured", {})
            requirement_version_id = data.get("requirement_version_id")
        return StageArtifact(
            artifact_id="",
            name=stage_value,
            content=content,
            status=ArtifactStatus.Stored,
            location=Path(file_path),
            structured_content=structured,
            project_id=project_id,
            attempt=attempt,
            requirement_version_id=requirement_version_id,
        )
