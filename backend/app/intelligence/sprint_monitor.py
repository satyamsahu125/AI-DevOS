from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..artifact.manager import ArtifactManager
    from ..workspace.manager import WorkspaceManager
    from .dependency_graph import ProjectDependencyGraph
    from .file_indexer import FileIndexer

logger = logging.getLogger(__name__)

_MAX_FILE_SUMMARIES = 15
_MAX_CRITICAL_FILES = 5


class SprintMonitor:
    """Monitors sprint execution integrity and provides cross-sprint context.

    Called by WorkflowManager before and after each sprint:

    Before sprint:
      - Generates a sprint brief with context from all previous sprints
      - Lists files already built so the developer agent doesn't recreate them
      - Surfaces critical shared files (most-depended-on)
      - Warns if architecture naming conventions are established

    After sprint:
      - Validates sprint deliverables against architecture data models
      - Detects missing models (planned but not implemented)
      - Records issues to project.json for human review (non-blocking)
    """

    def __init__(
        self,
        file_indexer: "FileIndexer",
        dependency_graph: "ProjectDependencyGraph",
        artifact_manager: "ArtifactManager",
        workspace_manager: "WorkspaceManager",
    ) -> None:
        self.indexer = file_indexer
        self.dep_graph = dependency_graph
        self.artifacts = artifact_manager
        self.workspace = workspace_manager

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_sprint_brief(
        self,
        project_id: str,
        sprint_number: int,
        sprint_goal: str,
    ) -> str:
        """Build a context brief for the upcoming sprint.

        Contains everything the sprint agents need to know about what
        previous sprints already built so they don't recreate files,
        import non-existent modules, or drift from established naming.

        Returns a formatted string ready for injection into agent prompts.
        """
        arch_summary = self._build_arch_summary(project_id)
        built_files = self.indexer.get_project_index(project_id)
        previous_files = [f for f in built_files if f.sprint_number < sprint_number]

        if not previous_files:
            return (
                f"SPRINT {sprint_number} BRIEF\n"
                f"Goal: {sprint_goal}\n"
                f"This is the FIRST sprint — no previous files exist yet.\n"
                f"{arch_summary}"
            )

        # Compact file summaries
        file_summaries = "\n".join(
            self.indexer.get_file_summary(project_id, f.file_path)
            for f in previous_files[:_MAX_FILE_SUMMARIES]
        )
        overflow = len(previous_files) - _MAX_FILE_SUMMARIES
        if overflow > 0:
            file_summaries += f"\n  ... and {overflow} more files"

        # Critical shared files
        critical = self.dep_graph.get_most_depended_on(project_id, top_n=_MAX_CRITICAL_FILES)
        critical_section = ""
        if critical:
            critical_section = (
                "\nCRITICAL FILES (most depended-on — do not break their interfaces):\n"
                + "\n".join(
                    f"  {path}  (imported by {count} other files)"
                    for path, count in critical
                )
            )

        return (
            f"SPRINT {sprint_number} BRIEF\n"
            f"Goal: {sprint_goal}\n"
            f"\n{arch_summary}"
            f"\nWHAT PREVIOUS SPRINTS BUILT ({len(previous_files)} files):\n"
            f"{file_summaries}"
            f"{critical_section}\n"
            f"\nINSTRUCTIONS FOR THIS SPRINT:\n"
            f"  - DO NOT recreate any file listed above\n"
            f"  - DO import and extend existing classes where applicable\n"
            f"  - MATCH the naming conventions already established\n"
            f"  - USE the same tech stack already in use\n"
            f"  - API endpoints must match the architecture contracts\n"
        )

    def validate_sprint_output(
        self,
        project_id: str,
        sprint_number: int,
    ) -> list[str]:
        """Validate sprint deliverables against the architecture.

        Returns a list of issue strings (empty = clean).
        Does NOT raise or block — callers should log and store issues,
        not abort the pipeline.
        """
        issues: list[str] = []
        arch = self.artifacts.get_artifact(project_id, self._architect_stage())
        if not arch or not arch.structured_content:
            return issues  # nothing to validate against

        arch_models: set[str] = {
            m.get("name", "").lower()
            for m in arch.structured_content.get("data_models", [])
            if m.get("name")
        }
        if not arch_models:
            return issues

        all_files = self.indexer.get_project_index(project_id)
        sprint_files = [f for f in all_files if f.sprint_number == sprint_number]
        all_classes: set[str] = {
            cls.lower()
            for f in all_files
            for cls in f.classes
        }
        sprint_classes: set[str] = {
            cls.lower()
            for f in sprint_files
            for cls in f.classes
        }

        for model in arch_models:
            if model not in all_classes:
                issues.append(
                    f"Architecture model '{model}' not found in any sprint output"
                )

        logger.debug(
            "Sprint %d validation: %d issues for project %s",
            sprint_number, len(issues), project_id,
        )
        return issues

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_arch_summary(self, project_id: str) -> str:
        arch = self.artifacts.get_artifact(project_id, self._architect_stage())
        if not arch or not arch.structured_content:
            return ""
        data = arch.structured_content
        tech = data.get("tech_stack", {})
        endpoints = data.get("api_endpoints", [])
        return (
            f"ARCHITECTURE CONTEXT:\n"
            f"  Tech stack: {tech}\n"
            f"  Total API endpoints planned: {len(endpoints)}\n"
        )

    @staticmethod
    def _architect_stage():
        from ..shared.enums.stage import Stage
        return Stage.Architect
