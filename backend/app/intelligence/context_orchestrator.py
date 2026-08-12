from __future__ import annotations

import logging
from typing import Any

from .code_summarizer import CodeSummarizer
from .dependency_graph import ProjectDependencyGraph
from .file_indexer import FileIndexer

logger = logging.getLogger(__name__)

# Stages that benefit from file-level context injection
_FILE_CONTEXT_STAGES = frozenset({"backend", "frontend", "qa", "BackendDeveloper", "FrontendDeveloper", "QA"})

# Which prerequisite stage artifacts each stage needs
_STAGE_NEEDS: dict[str, list[str]] = {
    "backend":          ["architect", "security", "file_planner"],
    "BackendDeveloper": ["architect", "security", "file_planner"],
    "frontend":         ["designer", "architect", "file_planner"],
    "FrontendDeveloper":["designer", "architect", "file_planner"],
    "qa":               ["product_owner"],
    "QA":               ["product_owner"],
    "devops":           ["architect", "security"],
    "DevOps":           ["architect", "security"],
    "document":         ["product_owner", "architect"],
    "Document":         ["product_owner", "architect"],
    "security":         ["architect"],
    "Security":         ["architect"],
    "file_planner":     ["architect", "sprint_planner"],
    "FileStructurePlanner": ["architect", "sprint_planner"],
    "sprint_planner":   ["architect", "designer"],
    "SprintPlanning":   ["architect", "designer"],
    "scrum_master":     ["sprint_planner"],
}


class ContextOrchestrator:
    """Builds a *relevant* context package for each agent call.

    Without this every agent receives the same raw predecessor message.
    With this each agent receives:

    * A compact project overview (what files exist, their purpose).
    * The subset of existing files most relevant to *this specific task*.
    * Dependency relationships between those files.
    * Prerequisite stage artifacts (architect spec, security review, …).
    * Past patterns from KnowledgeMemory that exceeded the similarity threshold.
    * Human-readable lessons from LessonStore for this stage/project.
    * Recent requirement-change descriptions.

    All in a structured :class:`ContextPackage` that
    :meth:`format_as_prompt_section` renders into a readable prompt prefix.
    """

    def __init__(
        self,
        file_indexer: FileIndexer,
        dependency_graph: ProjectDependencyGraph,
        code_summarizer: CodeSummarizer,
        knowledge_memory: Any,
        lesson_store: Any,
        artifact_manager: Any,
        workspace_manager: Any,
    ) -> None:
        self.indexer    = file_indexer
        self.dep_graph  = dependency_graph
        self.summarizer = code_summarizer
        self.knowledge  = knowledge_memory
        self.lessons    = lesson_store
        self.artifacts  = artifact_manager
        self.workspace  = workspace_manager

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def build(
        self,
        project_id: str,
        stage: str,
        task_description: str,
        include_file_context: bool | None = None,
    ) -> "ContextPackage":
        """Build a complete context package for *stage* / *task_description*.

        ``include_file_context`` defaults to ``True`` for backend, frontend,
        and QA stages; ``False`` for all others.  Pass an explicit value to
        override.
        """
        if include_file_context is None:
            include_file_context = stage in _FILE_CONTEXT_STAGES

        package = ContextPackage(stage=stage, task=task_description)

        # Load project.json once; used by both artifact staleness check and
        # requirement-changes injection below.  Non-fatal if unavailable.
        pj: dict = {}
        current_version_id: str | None = None
        try:
            pj = self.workspace.load_project_json(project_id) or {}
            current_version_id = pj.get("current_requirement_version_id") or None
        except Exception as exc:
            logger.debug("project.json load skipped: %s", exc)

        # 1. Compact project overview (always)
        package.project_overview = self.summarizer.build_project_overview(
            project_id, max_files=15
        )

        # 2. Relevant existing files
        if include_file_context:
            relevant_files = self.summarizer.get_relevant_files(
                project_id, task_description, max_files=6
            )
            for fp in relevant_files:
                package.relevant_files[fp] = self.summarizer.summarize_file(
                    project_id, fp, detail_level="medium"
                )

            # 3. Dependency relationships for those files
            if relevant_files:
                package.dependency_context = self.dep_graph.format_for_context(
                    project_id, relevant_files
                )

        # 4. Prerequisite stage artifacts (stale artifacts are excluded)
        package.stage_artifacts = self._load_stage_artifacts(
            project_id, stage, current_version_id=current_version_id
        )

        # 5. Past patterns (KnowledgeMemory semantic search)
        try:
            results = self.knowledge.search(
                query=f"{stage}: {task_description[:100]}",
                top_k=3,
                category_filter=f"{project_id}:{stage}",
            )
            package.past_patterns = [
                r.value[:200]
                for r in results
                if r.score > 0.6
            ]
        except Exception as exc:
            logger.debug("Pattern search skipped: %s", exc)

        # 6. Recent lessons (LessonStore)
        try:
            lesson_objs = self.lessons.get_lessons(
                stage=stage, project_id=project_id, limit=3
            )
            package.lessons = [
                l.what_worked for l in lesson_objs if l.what_worked
            ]
        except Exception as exc:
            logger.debug("Lesson load skipped: %s", exc)

        # 7. Requirement changes (reuses already-loaded pj)
        try:
            changes = pj.get("requirement_changes", [])
            if changes:
                package.requirement_changes = [
                    c["description"] for c in changes[-3:] if "description" in c
                ]
        except Exception as exc:
            logger.debug("Requirement changes load skipped: %s", exc)

        logger.info(
            "Context built for %s/%s: %d files, %d patterns, %d lessons",
            project_id, stage,
            len(package.relevant_files),
            len(package.past_patterns),
            len(package.lessons),
        )
        return package

    def get_project_state(self, project_id: str) -> dict:
        """Return structured intelligence state for *project_id*.

        Always returns a dict with all required fields — never None, never a
        partial dict.  Consumers check ``state["is_populated"]`` before using
        file-level data so Sprint 1 behaviour is preserved: the layer simply
        reports ``is_populated=False`` until the first ``index_project()`` pass.

        Fields
        ------
        files        List of indexed file paths; empty list before first sprint.
        symbols      Flat list of all class and function names across files.
        dependencies Reverse dependency graph ``{file: [files that import it]}``
                     as returned by ``ProjectDependencyGraph.build()``.
        summaries    Dict ``{file_path: one-line summary}`` built via
                     ``CodeSummarizer.summarize_file(detail_level="minimal")``.
        indexed_at   ISO-8601 timestamp of the most recently indexed file, or
                     empty string when no files are indexed yet.
        is_populated ``True`` when at least one file is in the index.

        Called by ``MemoryOrchestrator._load_intelligence()`` for Layer 4 assembly.
        """
        _empty: dict = {
            "files": [],
            "symbols": [],
            "dependencies": {},
            "summaries": {},
            "indexed_at": "",
            "is_populated": False,
        }
        try:
            indexed = self.indexer.get_project_index(project_id)
            if not indexed:
                return _empty

            file_paths = [f.file_path for f in indexed]

            # Collect all class and function names across the project
            symbols: list[str] = []
            for f in indexed:
                symbols.extend(f.classes)
                symbols.extend(f.functions)

            # Reverse dependency graph — non-fatal, falls back to empty dict
            dependencies: dict = {}
            try:
                dependencies = self.dep_graph.build(project_id)
            except Exception as _dep_exc:
                logger.debug(
                    "get_project_state: dep_graph.build skipped for %s: %s",
                    project_id, _dep_exc,
                )

            # Per-file one-line summaries — individual file errors are skipped
            summaries: dict[str, str] = {}
            for fp in file_paths:
                try:
                    summaries[fp] = self.summarizer.summarize_file(
                        project_id, fp, detail_level="minimal"
                    )
                except Exception as _sum_exc:
                    logger.debug(
                        "get_project_state: summarize_file skipped for %s/%s: %s",
                        project_id, fp, _sum_exc,
                    )

            indexed_at = max((f.last_updated for f in indexed), default="")

            return {
                "files": file_paths,
                "symbols": symbols,
                "dependencies": dependencies,
                "summaries": summaries,
                "indexed_at": indexed_at,
                "is_populated": True,
            }
        except Exception as exc:
            logger.debug("get_project_state failed for %s: %s", project_id, exc)
            return _empty

    # ------------------------------------------------------------------
    # Prompt formatting
    # ------------------------------------------------------------------

    def format_as_prompt_section(self, package: "ContextPackage") -> str:
        """Render *package* as a multi-section prompt prefix."""
        sections: list[str] = []

        if package.project_overview:
            sections.append("━━━ PROJECT OVERVIEW ━━━\n" + package.project_overview)

        if package.relevant_files:
            files_text = "\n\n".join(
                f"# {path}\n{summary}"
                for path, summary in package.relevant_files.items()
            )
            sections.append("━━━ RELEVANT EXISTING FILES ━━━\n" + files_text)

        if package.dependency_context:
            sections.append("━━━ DEPENDENCIES ━━━\n" + package.dependency_context)

        for stage_name, content in package.stage_artifacts.items():
            sections.append(f"━━━ {stage_name.upper()} OUTPUT ━━━\n" + content)

        if package.past_patterns:
            sections.append(
                "━━━ PATTERNS FROM PAST RUNS ━━━\n"
                + "\n".join(f"  - {p}" for p in package.past_patterns)
            )

        if package.lessons:
            sections.append(
                "━━━ LESSONS LEARNED ━━━\n"
                + "\n".join(f"  - {l}" for l in package.lessons)
            )

        if package.requirement_changes:
            sections.append(
                "━━━ RECENT REQUIREMENT CHANGES ━━━\n"
                + "\n".join(f"  - {c}" for c in package.requirement_changes)
            )

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_stage_artifacts(
        self,
        project_id: str,
        current_stage: str,
        *,
        current_version_id: str | None = None,
    ) -> dict[str, str]:
        """Load and truncate prerequisite stage artifacts.

        Artifacts whose ``requirement_version_id`` does not match
        ``current_version_id`` are considered STALE and excluded from context.
        Legacy artifacts (no ``requirement_version_id``) are always included for
        backward compatibility.  When ``current_version_id`` is None the
        staleness check is skipped entirely.
        """
        needed = _STAGE_NEEDS.get(current_stage, [])
        result: dict[str, str] = {}

        # ArtifactManager.get_artifact expects a Stage enum — try both str and enum
        for stage_name in needed:
            try:
                from ..shared.enums.stage import Stage
                try:
                    stage_enum = Stage(stage_name)
                except ValueError:
                    # Try case-insensitive match
                    stage_enum = next(
                        (s for s in Stage if s.value.lower() == stage_name.lower()),
                        None,
                    )
                if stage_enum is None:
                    continue
                art = self.artifacts.get_artifact(project_id, stage_enum)
                if not art or not art.content:
                    continue
                if art.is_stale(current_version_id):
                    logger.info(
                        "Stale artifact excluded from context: project=%s stage=%s "
                        "artifact_version=%s current_version=%s",
                        project_id, stage_name,
                        art.requirement_version_id, current_version_id,
                    )
                    continue
                content = art.content
                if len(content) > 2000:
                    content = content[:2000] + "\n...[truncated]"
                result[stage_name] = content
            except Exception as exc:
                logger.debug("Artifact load skipped for %s: %s", stage_name, exc)

        return result


class ContextPackage:
    """Structured context assembled for one agent invocation."""

    def __init__(self, stage: str, task: str) -> None:
        self.stage = stage
        self.task = task
        self.project_overview: str = ""
        self.relevant_files: dict[str, str] = {}
        self.dependency_context: str = ""
        self.stage_artifacts: dict[str, str] = {}
        self.past_patterns: list[str] = []
        self.lessons: list[str] = []
        self.requirement_changes: list[str] = []
