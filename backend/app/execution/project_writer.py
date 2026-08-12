from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from pydantic import BaseModel, Field

from ..workspace.manager import WorkspaceManager

if TYPE_CHECKING:
    from ..intelligence.file_indexer import FileIndexer

logger = logging.getLogger(__name__)

# Regex: matches an opening code-fence line (```python, ```jsx, ``` etc.)
# anchored at the very start of the content (possibly after whitespace).
_FENCE_OPEN_RE = re.compile(r"^\s*```[a-zA-Z0-9]*\s*\n", re.MULTILINE)
# Regex: matches a closing code-fence line (``` alone on a line).
# Uses [ \t]* (not \s*) to avoid consuming the trailing newline that follows the fence.
_FENCE_CLOSE_RE = re.compile(r"\n[ \t]*```[ \t]*$", re.MULTILINE)


def _strip_code_fences(content: str, file_path: str) -> str:
    """Strip LLM markdown code-fence wrappers from generated source files.

    Some models (Qwen3, etc.) wrap their output in ```python ... ``` or
    similar blocks despite system-prompt instructions not to.  Writing those
    fences to disk causes SyntaxErrors for Python files and import failures
    for JS/TS.

    Only strips fences for source-code file types; leaves other files (Markdown,
    YAML, etc.) untouched.
    """
    source_extensions = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
        ".html", ".css", ".scss",
    }
    ext = Path(file_path).suffix.lower()
    if ext not in source_extensions:
        return content

    stripped = content
    # Strip a leading opening fence (e.g. "```python\n" at start of file)
    stripped = _FENCE_OPEN_RE.sub("", stripped, count=1)
    # Strip a trailing closing fence ("```" at very end of file)
    stripped = _FENCE_CLOSE_RE.sub("", stripped)
    if stripped != content:
        logger.warning(
            "ProjectWriter: stripped markdown code fences from %s (%d → %d bytes)",
            file_path, len(content), len(stripped),
        )
    return stripped


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

    def __init__(
        self,
        workspace_manager: WorkspaceManager | None = None,
        file_indexer: "FileIndexer | None" = None,
    ) -> None:
        self.workspace = workspace_manager or WorkspaceManager()
        self._file_indexer = file_indexer
        self._current_sprint: int = 0

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

        # Strip LLM markdown code-fence wrappers before writing to disk.
        # Prevents ```python ... ``` from leaking into source files and
        # causing SyntaxErrors or import failures at runtime.
        content = _strip_code_fences(content, file_path)

        # Write the file
        full_path.write_text(content, encoding="utf-8")

        # Keep attempt history (_attempt_1_test_auth.py)
        history_path = full_path.parent / f"_attempt_{attempt}_{full_path.name}"
        history_path.write_text(content, encoding="utf-8")

        logger.info("Written: %s (%d bytes)", full_path, len(content))

        # Auto-index via FileIndexer (no LLM — pure AST/regex)
        if self._file_indexer is not None:
            try:
                self._file_indexer.index_file(
                    project_id=project_id,
                    file_path=file_path,
                    content=content,
                    sprint_number=self._current_sprint,
                )
            except Exception as _idx_exc:
                logger.debug("FileIndexer.index_file skipped: %s", _idx_exc)

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

    def apply_patch(self, project_id: str, file_path: str, search_block: str, replace_block: str, attempt: int = 1) -> WrittenFile:
        """Apply a targeted search-and-replace patch to an existing file."""
        content = self.read_file(project_id, file_path)
        if content is None:
            raise FileNotFoundError(f"Cannot patch non-existent file: {file_path}")
            
        # Normalize line endings to avoid \r\n vs \n mismatch
        normalized_content = content.replace("\r\n", "\n")
        normalized_search = search_block.replace("\r\n", "\n")
        
        if normalized_search not in normalized_content:
            raise ValueError(f"Search block not found in {file_path}. Ensure exact match including whitespace.")
            
        new_content = normalized_content.replace(normalized_search, replace_block, 1)
        return self.write_file(project_id, file_path, new_content, attempt)

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
