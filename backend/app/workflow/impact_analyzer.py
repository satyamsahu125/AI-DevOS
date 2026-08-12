from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from ..shared.schemas.requirement_change_schema import (
    ImpactAnalysis,
    RequirementChange,
)

logger = logging.getLogger(__name__)

# Which stages depend on which earlier stages
STAGE_DEPENDENCIES: dict[str, list[str]] = {
    "strategic_review": [],
    "product_owner": ["strategic_review"],
    "architect": ["product_owner"],
    "designer": ["architect"],
    "security": ["architect"],
    "sprint_planner": ["security"],
    "scrum_master": ["sprint_planner"],
    "file_planner": ["scrum_master"],
    "backend": ["file_planner", "security", "architect"],
    "frontend": ["file_planner", "designer", "architect"],
    "qa": ["backend", "frontend"],
    "document": ["qa"],
    "devops": ["document", "security"],
    "retro": ["devops"],
}

# Which change types affect which stages
CHANGE_TYPE_IMPACT: dict[str, list[str]] = {
    "add_feature": [
        "product_owner",
        "architect",
        "sprint_planner",
        "scrum_master",
        "file_planner",
        "backend",
        "frontend",
        "qa",
        "document",
    ],
    "remove_feature": [
        "product_owner",
        "architect",
        "file_planner",
        "backend",
        "frontend",
        "qa",
        "document",
    ],
    "modify_ui": ["designer", "frontend", "qa"],
    "modify_api": [
        "architect",
        "security",
        "file_planner",
        "backend",
        "frontend",
        "qa",
        "document",
    ],
    "modify_database": ["architect", "file_planner", "backend", "qa"],
    "modify_auth": [
        "architect",
        "security",
        "file_planner",
        "backend",
        "frontend",
        "qa",
    ],
    "change_scale": ["architect", "security", "devops"],
}


class ImpactAnalyzer:
    """Analyzes which stages need to re-run when a requirement changes between sprints.

    Uses LLM to classify change type, then applies dependency rules to find affected stages.

    For post-sprint partial changes, ``analyze_file_impact()`` uses FileIndexer +
    DependencyGraph to identify specific files rather than whole stages.
    """

    def __init__(
        self,
        llm_manager,
        artifact_manager,
        file_indexer=None,
        dep_graph=None,
        code_summarizer=None,
        workspace_manager=None,
    ) -> None:
        self.llm = llm_manager
        self.artifacts = artifact_manager
        self._file_indexer = file_indexer
        self._dep_graph = dep_graph
        self._code_summarizer = code_summarizer
        self._workspace_manager = workspace_manager

    def analyze(
        self,
        project_id: str,
        change_description: str,
        stages_completed: list[str],
    ) -> ImpactAnalysis:
        """Analyze the impact of a requirement change.

        Returns which stages must re-run and which can be kept.
        """
        logger.info(
            "Analyzing impact for project %s: %s",
            project_id,
            change_description[:80],
        )

        # Step 1: Classify what type of change this is
        change_type = self._classify_change(change_description)

        # Step 2: Find directly affected stages
        directly_affected = set(
            CHANGE_TYPE_IMPACT.get(
                change_type,
                [
                    "product_owner",
                    "architect",
                    "file_planner",
                    "backend",
                    "frontend",
                    "qa",
                ],
            )
        )

        # Step 3: Add downstream stages (cascading impact)
        all_affected = self._add_downstream(directly_affected, stages_completed)

        # Step 4: What can be preserved
        safe_stages = [s for s in stages_completed if s not in all_affected]

        # Step 5: Identify affected files
        affected_files = self._find_affected_files(project_id, list(all_affected))

        # Step 6: Which sprints need replanning
        code_stages = {"backend", "frontend"}
        needs_replan = bool(all_affected.intersection(code_stages))

        explanation = self._build_explanation(
            change_description, change_type, list(all_affected), safe_stages
        )

        analysis = ImpactAnalysis(
            change_id=str(uuid4()),
            project_id=project_id,
            analyzed_at=datetime.now(timezone.utc),
            description=change_description,
            affected_stages=sorted(
                list(all_affected),
                key=lambda s: list(STAGE_DEPENDENCIES.keys()).index(s)
                if s in STAGE_DEPENDENCIES
                else 99,
            ),
            safe_stages=safe_stages,
            affected_files=affected_files[:20],
            sprints_to_replan=self._compute_sprints_to_replan(project_id) if needs_replan else [],
            estimated_rerun_time=f"~{len(all_affected)} stages",
            explanation=explanation,
            can_preserve=safe_stages,
        )

        logger.info(
            "Impact analysis: %d stages affected, %d preserved for project %s",
            len(all_affected),
            len(safe_stages),
            project_id,
        )
        return analysis

    def analyze_file_impact(
        self,
        project_id: str,
        change_description: str,
    ) -> dict:
        """File-level impact analysis for partial changes within a sprint.

        Uses FileIndexer + DependencyGraph to identify specific files to regenerate
        rather than whole stages. Appropriate when code files already exist on disk
        (i.e. at least one sprint has completed).

        Returns a dict with:
          files_to_regenerate  — files touched by this change
          files_safe           — files unaffected
          total_affected       — count of files to regenerate
          total_preserved      — count of safe files
          explanation          — human-readable summary
        """
        if self._code_summarizer is None or self._dep_graph is None or self._file_indexer is None:
            return {
                "change_description": change_description,
                "files_to_regenerate": [],
                "files_safe": [],
                "total_affected": 0,
                "total_preserved": 0,
                "explanation": "File-level analysis not available (intelligence layer not wired).",
            }

        try:
            # Find files relevant to this change by keyword
            relevant = self._code_summarizer.get_relevant_files(
                project_id=project_id,
                task_description=change_description,
                max_files=10,
            )

            # Expand to all transitive dependents (BFS)
            all_affected: set[str] = set(relevant)
            for fp in relevant:
                dependents = self._dep_graph.get_impact(project_id, fp)
                all_affected.update(dependents)

            # Separate built vs safe
            built_paths = {f.file_path for f in self._file_indexer.get_project_index(project_id)}
            files_to_regenerate = sorted(all_affected & built_paths)
            files_safe = sorted(built_paths - all_affected)

            return {
                "change_description": change_description,
                "files_to_regenerate": files_to_regenerate,
                "files_safe": files_safe,
                "total_affected": len(files_to_regenerate),
                "total_preserved": len(files_safe),
                "explanation": (
                    f"Change affects {len(files_to_regenerate)} file(s). "
                    f"{len(files_safe)} file(s) are unchanged."
                ),
            }
        except Exception as exc:
            logger.warning("analyze_file_impact failed: %s", exc)
            return {
                "change_description": change_description,
                "files_to_regenerate": [],
                "files_safe": [],
                "total_affected": 0,
                "total_preserved": 0,
                "explanation": f"File-level analysis error: {exc}",
            }

    def _classify_change(self, description: str) -> str:
        """Use LLM to classify the change type."""
        prompt = f"""
Classify this requirement change into one of these types:
  add_feature        - adding a new feature
  remove_feature     - removing an existing feature
  modify_ui          - changing the UI/design only
  modify_api         - changing API endpoints or contracts
  modify_database    - changing data models or storage
  modify_auth        - changing authentication/authorization
  change_scale       - changing performance/scale requirements

Requirement change: {description}

Reply with ONLY the type name, nothing else.
Example: add_feature
"""
        try:
            result = self.llm.generate_text(
                prompt=prompt,
                system_prompt=(
                    "You classify software requirement changes. "
                    "Reply with only the type name."
                ),
            ).content.strip().lower()

            valid_types = CHANGE_TYPE_IMPACT.keys()
            if result in valid_types:
                return result
            # Fallback if LLM returns unexpected value
            return "add_feature"
        except Exception as e:
            logger.warning("Change classification failed: %s", e)
            return "add_feature"

    def _add_downstream(
        self,
        directly_affected: set[str],
        completed: list[str],
    ) -> set[str]:
        """Add all stages downstream of affected stages."""
        all_affected = set(directly_affected)
        changed = True
        while changed:
            changed = False
            for stage, deps in STAGE_DEPENDENCIES.items():
                if stage in completed and stage not in all_affected:
                    if any(d in all_affected for d in deps):
                        all_affected.add(stage)
                        changed = True
        return all_affected

    def _find_affected_files(
        self,
        project_id: str,
        affected_stages: list[str],
    ) -> list[str]:
        """Find files that will be regenerated."""
        files = []
        for stage_str in affected_stages:
            stage_enum = None
            try:
                from ..shared.enums.stage import Stage
                from .stage_lookup import resolve_stage_name
                canonical = resolve_stage_name(stage_str)
                stage_enum = Stage(canonical)
            except Exception:
                pass

            artifact = None
            if stage_enum and self.artifacts:
                try:
                    artifact = self.artifacts.get_artifact(project_id, stage_enum)
                except Exception:
                    pass

            if artifact and artifact.structured_content:
                planned = artifact.structured_content.get("planned_paths", [])
                if isinstance(planned, list):
                    files.extend(planned[:5])
        return files

    def _compute_sprints_to_replan(self, project_id: str) -> list[int]:
        """Return sprint numbers not yet completed, sorted ascending.

        Reads sprint state from project.json via workspace_manager:
          - sprint_plan.sprints[].sprint_number — all planned sprints
          - completed_sprints                   — sprint numbers already done

        A sprint is included if its number does NOT appear in completed_sprints.
        This is deterministic: identical project state → identical result.

        Returns [] when workspace_manager is absent, or when no sprint_plan
        exists yet (i.e. the sprint planner stage has not run).
        """
        if self._workspace_manager is None:
            return []
        try:
            data = self._workspace_manager.load_project_json(project_id) or {}
            sprint_plan_data = data.get("sprint_plan")
            if not sprint_plan_data:
                return []
            sprints = sprint_plan_data.get("sprints", [])
            completed: set[int] = set(data.get("completed_sprints") or [])
            return sorted(
                s["sprint_number"]
                for s in sprints
                if isinstance(s.get("sprint_number"), int)
                and s["sprint_number"] not in completed
            )
        except Exception as exc:
            logger.warning(
                "[ImpactAnalyzer] _compute_sprints_to_replan failed "
                "(returning []): project=%s error=%s",
                project_id,
                exc,
            )
            return []

    def _build_explanation(
        self,
        description: str,
        change_type: str,
        affected: list[str],
        safe: list[str],
    ) -> str:
        type_labels = {
            "add_feature": "adding a new feature",
            "remove_feature": "removing a feature",
            "modify_ui": "a UI change",
            "modify_api": "an API change",
            "modify_database": "a database change",
            "modify_auth": "an authentication change",
            "change_scale": "a scale/performance change",
        }
        label = type_labels.get(change_type, "this change")
        return (
            f"Your change '{description[:60]}' is classified "
            f"as {label}. This requires re-running "
            f"{len(affected)} stage(s): "
            f"{', '.join(affected[:4])}"
            + (f" and {len(affected)-4} more" if len(affected) > 4 else "")
            + f". {len(safe)} stage(s) can be preserved: "
            + (", ".join(safe[:3]) if safe else "none")
            + "."
        )
