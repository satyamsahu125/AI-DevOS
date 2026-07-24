from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..execution.safety_policy import OperationType, SafetyDecision, SafetyException, SafetyPolicy
from .manager import WorkspaceManager


@dataclass(slots=True)
class WrittenFile:
    """One real project file ProjectFileManager wrote to disk."""

    path: str
    absolute_path: Path
    bytes_written: int


class ProjectFileManager:
    """Writes real, runnable project files into temp-workspace/{project_id}/project/{area}/.

    Unlike ArtifactManager (which persists a stage's LLM output as a
    reviewable document under artifacts/), this writes the actual generated
    source files a human could cd into and run -- one file per
    write_file() call, safety-checked the same way ArtifactManager's writes
    are (see SafetyPolicy, inspired by gstack's /careful skill), so an
    unapproved earlier attempt's file is never silently clobbered.
    """

    def __init__(self, workspace_manager: WorkspaceManager | None = None, safety_policy: SafetyPolicy | None = None) -> None:
        """Wire the WorkspaceManager used to resolve project_id's real project root and the
        SafetyPolicy checked before every write.

        SafetyPolicy's own default workspace_root is the backend/ directory,
        which only matches WorkspaceManager's default root by coincidence --
        an isolated WorkspaceManager (e.g. one rooted at a temp dir in tests)
        would otherwise have every one of its overwrites misclassified as
        "outside the workspace" and BLOCKed. Defaulting SafetyPolicy's root
        to this WorkspaceManager's root keeps the two in sync.
        """
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.safety_policy = safety_policy or SafetyPolicy(workspace_root=self.workspace_manager.root)

    def project_root(self, project_id: str) -> Path:
        """Return project_id's real generated-project root (temp-workspace/{project_id}/project/)."""
        return self.workspace_manager.get_workspace_path(project_id) / "project"

    def area_dir(self, project_id: str, area: str) -> Path:
        """Return project_id's real generated-project subdirectory for area (e.g. "backend", "frontend")."""
        return self.project_root(project_id) / area

    def write_file(self, project_id: str, area: str, relative_path: str, content: str, *, attempt: int = 1) -> WrittenFile:
        """Write content to project_id's real project/{area}/{relative_path}, after a SafetyPolicy check."""
        safe_relative_path = self._sanitize_relative_path(relative_path)
        target = self.area_dir(project_id, area) / safe_relative_path
        decision = self.safety_policy.check(OperationType.FILE_OVERWRITE, str(target), attempt=attempt)
        if decision.decision == SafetyDecision.BLOCK:
            raise SafetyException(decision.reason)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return WrittenFile(path=safe_relative_path, absolute_path=target, bytes_written=len(content.encode("utf-8")))

    @staticmethod
    def _sanitize_relative_path(relative_path: str) -> str:
        """Normalize an LLM-authored path so it can never escape area_dir.

        A leading "/" (or "\\") is the actual root cause of a real bug: Path("area") / "/x/y"
        is an ABSOLUTE path in pathlib, so the "/" operator silently discards the "area" prefix
        entirely and the write lands outside the project directory instead of raising -- this
        stripped every leading separator, so "/api/users/register" becomes "api/users/register"
        and joins normally. ".." components are rejected outright as path traversal.
        """
        normalized = relative_path.replace("\\", "/").lstrip("/")
        parts = [part for part in normalized.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts):
            raise SafetyException(f"path traversal is not permitted: {relative_path}")
        if not parts:
            raise SafetyException(f"empty file path is not permitted: {relative_path!r}")
        return "/".join(parts)

    def list_written(self, project_id: str, area: str) -> list[str]:
        """Return every file path (relative to area_dir, forward-slashed) written so far for project_id/area."""
        root = self.area_dir(project_id, area)
        if not root.exists():
            return []
        return sorted(str(path.relative_to(root)).replace("\\", "/") for path in root.rglob("*") if path.is_file())
