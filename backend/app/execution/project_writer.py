from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field

from ..workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)


class WrittenFile(BaseModel):
    """Metadata for a generated file written to disk."""

    file_path: str
    absolute_path: str
    size_bytes: int
    attempt: int
    written_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProjectWriter:
    """Writes generated code to real files in the project directory.

    The project directory is: temp-workspace/{project_id}/project/ This is the
    component that makes code real.
    """

    def __init__(self, workspace_manager: WorkspaceManager | None = None) -> None:
        self.workspace = workspace_manager or WorkspaceManager()

    def get_project_dir(self, project_id: str) -> Path:
        """Returns temp-workspace/{project_id}/project/"""
        return self.workspace.get_workspace_path(project_id) / "project"

    def write_file(self, project_id: str, file_path: str, content: str, attempt: int = 1) -> WrittenFile:
        """Write generated code to real file on disk.

        Creates parent directories automatically. Keeps attempt history.
        Returns WrittenFile with absolute path.
        """
        project_dir = self.get_project_dir(project_id)
        full_path = project_dir / file_path

        # Create parent directories
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the file
        full_path.write_text(content, encoding="utf-8")

        # Keep attempt history (_attempt_1_test_auth.py)
        history_path = full_path.parent / f"_attempt_{attempt}_{full_path.name}"
        history_path.write_text(content, encoding="utf-8")

        logger.info("Written: %s (%d bytes)", full_path, len(content))

        return WrittenFile(
            file_path=file_path,
            absolute_path=str(full_path),
            size_bytes=len(content),
            attempt=attempt,
            written_at=datetime.now(timezone.utc),
        )

    def file_exists(self, project_id: str, file_path: str) -> bool:
        """Check if file already exists in project."""
        full_path = self.get_project_dir(project_id) / file_path
        return full_path.exists()

    def read_file(self, project_id: str, file_path: str) -> str | None:
        """Read an existing project file (for dependency context)."""
        full_path = self.get_project_dir(project_id) / file_path
        if full_path.exists():
            return full_path.read_text(encoding="utf-8")
        return None

    def list_files(self, project_id: str) -> list[str]:
        """List all files in the project directory."""
        project_dir = self.get_project_dir(project_id)
        if not project_dir.exists():
            return []
        return [
            str(p.relative_to(project_dir)).replace("\\", "/")
            for p in project_dir.rglob("*")
            if p.is_file() and ".attempt-" not in p.name and "_attempt_" not in p.name
        ]

    def initialize_project(self, project_id: str, tech_stack: dict | None = None) -> None:
        """Create project directory structure."""
        project_dir = self.get_project_dir(project_id)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create standard directories
        for dir_name in ["backend", "frontend", "tests", ".github/workflows"]:
            (project_dir / dir_name).mkdir(parents=True, exist_ok=True)

        logger.info("Project directory initialized: %s", project_dir)
