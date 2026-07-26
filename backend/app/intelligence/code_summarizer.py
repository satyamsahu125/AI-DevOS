from __future__ import annotations

import logging

from .file_indexer import FileIndexer, FileMetadata

logger = logging.getLogger(__name__)

# Files smaller than this threshold are sent as full content;
# larger ones are replaced with a structured summary.
FULL_FILE_THRESHOLD = 1500


class CodeSummarizer:
    """Produces compact file summaries for agent context.

    On small projects: sends full file content.
    On large projects: sends summary + key sections.
    Never overflows the context window.
    """

    def __init__(self, file_indexer: FileIndexer) -> None:
        self.indexer = file_indexer

    # ------------------------------------------------------------------
    # Per-file summarisation
    # ------------------------------------------------------------------

    def summarize_file(
        self,
        project_id: str,
        file_path: str,
        full_content: str | None = None,
        detail_level: str = "medium",
    ) -> str:
        """Return an appropriate representation of *file_path*.

        ``detail_level`` controls verbosity:
          * ``"minimal"`` — one-line header only
          * ``"medium"``  — purpose + classes + key functions (default)
          * ``"full"``    — complete content when small; summary + head otherwise
        """
        summary = self.indexer.get_file_summary(project_id, file_path)

        if detail_level == "minimal":
            return summary.split("\n")[0] if summary else file_path

        if detail_level == "full" and full_content is not None:
            if len(full_content) <= FULL_FILE_THRESHOLD:
                return f"# {file_path}\n```\n{full_content}\n```"
            return (
                f"{summary}\nFirst 500 chars:\n```\n{full_content[:500]}\n...\n```"
            )

        return summary  # "medium"

    # ------------------------------------------------------------------
    # Project-wide overview
    # ------------------------------------------------------------------

    def build_project_overview(
        self, project_id: str, max_files: int = 20
    ) -> str:
        """Build a compact overview of the entire project.

        Groups files by top-level directory and lists them with their
        purpose and class names so an agent can understand the full
        codebase without reading every file.
        """
        files = self.indexer.get_project_index(project_id)
        if not files:
            return "No files generated yet."

        # Group by top-level directory
        groups: dict[str, list[FileMetadata]] = {}
        for f in files:
            parts = f.file_path.split("/")
            group = parts[0] if len(parts) > 1 else "root"
            groups.setdefault(group, []).append(f)

        lines = [f"PROJECT STRUCTURE ({len(files)} files total):"]

        per_group = max(1, max_files // max(len(groups), 1))
        for group, group_files in sorted(groups.items()):
            lines.append(f"\n{group}/")
            for f in sorted(group_files, key=lambda x: x.file_path)[:per_group]:
                name = f.file_path.split("/")[-1]
                purpose = (
                    (f.purpose[:60] + "...") if len(f.purpose) > 60 else f.purpose
                )
                classes = (
                    f" [{', '.join(f.classes[:2])}]" if f.classes else ""
                )
                lines.append(
                    f"  {name}{classes}"
                    + (f"\n    {purpose}" if purpose else "")
                )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Relevance ranking
    # ------------------------------------------------------------------

    def get_relevant_files(
        self,
        project_id: str,
        task_description: str,
        max_files: int = 8,
    ) -> list[str]:
        """Return the file paths most relevant to *task_description*.

        Uses simple keyword matching against class names, function names,
        and purpose strings — fast, deterministic, no LLM required.
        """
        task_words = set(task_description.lower().split())
        files = self.indexer.get_project_index(project_id)

        scored: list[tuple[str, int]] = []
        for f in files:
            score = 0
            for cls in f.classes:
                if any(w in cls.lower() for w in task_words):
                    score += 3
            for func in f.functions:
                if any(w in func.lower() for w in task_words):
                    score += 2
            if f.purpose and any(w in f.purpose.lower() for w in task_words):
                score += 1
            if f.file_path and any(w in f.file_path.lower() for w in task_words):
                score += 1
            if score > 0:
                scored.append((f.file_path, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [path for path, _ in scored[:max_files]]
