from __future__ import annotations

import json
import logging
from collections import defaultdict, deque

from .file_indexer import FileIndexer

logger = logging.getLogger(__name__)


class ProjectDependencyGraph:
    """Maps which files depend on which other files.

    Built automatically from :class:`FileIndexer` import analysis —
    no LLM calls, pure graph traversal.

    Answers:
      "If AuthService changes, what else might break?"
      "What does UserController depend on?"
      "What are the entry points (files nothing imports)?"
    """

    def __init__(self, file_indexer: FileIndexer) -> None:
        self.indexer = file_indexer

    # ------------------------------------------------------------------
    # Core graph operations
    # ------------------------------------------------------------------

    def build(self, project_id: str) -> dict[str, list[str]]:
        """Build the reverse dependency graph for *project_id*.

        Returns ``{depended_on_file: [files_that_import_it]}``.
        """
        files = self.indexer.get_project_index(project_id)
        graph: dict[str, list[str]] = defaultdict(list)
        file_paths = {f.file_path for f in files}

        for file_meta in files:
            for dep in file_meta.dependencies:
                resolved = self._resolve_import(dep, file_meta.file_path, file_paths)
                if resolved:
                    graph[resolved].append(file_meta.file_path)

        return dict(graph)

    def get_impact(self, project_id: str, changed_file: str) -> list[str]:
        """Return every file that transitively depends on *changed_file*.

        Uses BFS over the reverse dependency graph so the full blast
        radius of a change is captured, not just direct importers.
        """
        graph = self.build(project_id)
        visited: set[str] = set()
        queue: deque[str] = deque([changed_file])

        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            for dependent in graph.get(current, []):
                if dependent not in visited:
                    queue.append(dependent)

        visited.discard(changed_file)
        return sorted(visited)

    def get_dependencies_of(self, project_id: str, file_path: str) -> list[str]:
        """Return the direct dependencies of *file_path* (what it imports)."""
        for f in self.indexer.get_project_index(project_id):
            if f.file_path == file_path:
                return f.dependencies
        return []

    def get_entry_points(self, project_id: str) -> list[str]:
        """Return files that nothing else imports — the top-level entry points."""
        graph = self.build(project_id)
        all_files = {f.file_path for f in self.indexer.get_project_index(project_id)}
        return sorted(all_files - set(graph.keys()))

    def get_most_depended_on(
        self, project_id: str, top_n: int = 5
    ) -> list[tuple[str, int]]:
        """Return the *top_n* most-imported files (core/shared utilities)."""
        graph = self.build(project_id)
        ranked = sorted(graph.items(), key=lambda x: len(x[1]), reverse=True)
        return [(path, len(deps)) for path, deps in ranked[:top_n]]

    # ------------------------------------------------------------------
    # Prompt formatting
    # ------------------------------------------------------------------

    def format_for_context(
        self, project_id: str, relevant_files: list[str]
    ) -> str:
        """Format dependency relationships as readable text for agent prompts."""
        if not relevant_files:
            return ""

        lines = ["DEPENDENCY RELATIONSHIPS:"]
        for file_path in relevant_files[:10]:
            deps = self.get_dependencies_of(project_id, file_path)
            impact = self.get_impact(project_id, file_path)
            name = file_path.split("/")[-1]
            if deps:
                lines.append(
                    f"  {name} depends on: "
                    + ", ".join(d.split("/")[-1] for d in deps[:3])
                )
            if impact:
                lines.append(
                    f"  Changes to {name} affect: "
                    + ", ".join(i.split("/")[-1] for i in impact[:3])
                )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Import resolution
    # ------------------------------------------------------------------

    def _resolve_import(
        self, import_str: str, from_file: str, known_files: set[str]
    ) -> str | None:
        """Try to map an import string to a known file path."""
        # Normalise: strip leading dots (relative imports)
        stripped = import_str.lstrip(".")
        candidates = [
            stripped.replace(".", "/") + ".py",
            stripped.replace(".", "/") + ".ts",
            stripped.replace(".", "/") + "/index.ts",
            stripped.replace(".", "/") + "/index.js",
        ]
        for candidate in candidates:
            if candidate in known_files:
                return candidate
        return None
