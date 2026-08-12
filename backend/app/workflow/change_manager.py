"""ChangeManager — single responsibility: requirement change analysis and application.

Extracted from WorkflowManager.submit_requirement_change() and
WorkflowManager.apply_requirement_change().
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from ..shared.enums.project_state import ProjectState

logger = logging.getLogger(__name__)

# Stage names (both canonical and CamelCase aliases) that correspond to sprint
# execution work.  When any of these appear in affected_stages the sprint plan
# must be marked stale.
_CODE_STAGES: frozenset[str] = frozenset(
    {"backend", "frontend", "BackendDeveloper", "FrontendDeveloper"}
)


class ChangeManager:
    """Handles requirement change analysis and staged application.

    Parameters
    ----------
    workspace_manager:
        Reads/writes project.json and stage state.
    impact_analyzer:
        Analyses which stages are affected by a change description.
    broadcaster:
        Pushes change_analyzed events to connected clients.
    transition_fn:
        Callable(project_id, new_state) → None for state transitions.
    """

    def __init__(
        self,
        workspace_manager: Any,
        impact_analyzer: Any,
        broadcaster: Any,
        transition_fn: Any,
    ) -> None:
        self._workspace = workspace_manager
        self._impact_analyzer = impact_analyzer
        self._broadcaster = broadcaster
        self._transition = transition_fn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, project_id: str, change_description: str) -> Any:
        """Analyse a change request and store it in project.json.

        Returns the ImpactAnalysis object (does NOT start re-running).
        The user must call apply() to confirm.
        """
        pj = self._workspace.load_project_json(project_id) or {}
        stages_completed = pj.get("stages_completed", [])

        # File-level impact when code already exists.
        code_stages = {"backend", "frontend", "BackendDeveloper", "FrontendDeveloper"}
        if (
            any(s in code_stages for s in stages_completed)
            and hasattr(self._impact_analyzer, "analyze_file_impact")
        ):
            try:
                file_impact = self._impact_analyzer.analyze_file_impact(
                    project_id=project_id,
                    change_description=change_description,
                )
                logger.info(
                    "File-level impact for %s: %d affected, %d preserved",
                    project_id,
                    file_impact.get("total_affected", 0),
                    file_impact.get("total_preserved", 0),
                )
                self._workspace.update_project_json(
                    project_id, {"file_impact_analysis": file_impact},
                )
            except Exception as exc:
                logger.debug("file-level impact analysis failed (non-fatal): %s", exc)

        analysis = self._impact_analyzer.analyze(
            project_id=project_id,
            change_description=change_description,
            stages_completed=stages_completed,
        )

        self._workspace.update_project_json(project_id, {
            "pending_change": {
                "change_id": analysis.change_id,
                "description": change_description,
                "affected_stages": analysis.affected_stages,
                "safe_stages": analysis.safe_stages,
                "analyzed_at": analysis.analyzed_at.isoformat(),
            }
        })
        self._transition(project_id, ProjectState.CHANGE_REQUESTED)
        self._broadcaster.change_analyzed(
            project_id=project_id,
            affected_stages=analysis.affected_stages,
            safe_stages=analysis.safe_stages,
        )
        logger.info(
            "Requirement change submitted for %s: %d affected stages",
            project_id, len(analysis.affected_stages),
        )
        return analysis

    def apply(
        self,
        project_id: str,
        change_id: str,
        confirmed: bool,
        user_comment: str = "",
    ) -> dict:
        """Apply or cancel a previously submitted change.

        If confirmed=False, reverts to SPRINT_IN_PROGRESS without touching
        stages_completed.  If confirmed=True, removes affected stages from
        stages_completed so the pipeline re-runs from the first affected stage.
        """
        if not confirmed:
            self._workspace.update_project_json(project_id, {"pending_change": None})
            self._transition(project_id, ProjectState.SPRINT_IN_PROGRESS)
            return {"status": "cancelled"}

        pj = self._workspace.load_project_json(project_id) or {}
        pending = pj.get("pending_change", {})
        if pending.get("change_id") != change_id:
            raise ValueError(f"Change ID mismatch: expected {change_id}, got {pending.get('change_id')}")

        affected = pending.get("affected_stages", [])
        safe_stages = pending.get("safe_stages", [])

        changes = pj.get("requirement_changes", [])
        changes.append({
            "change_id": change_id,
            "description": pending.get("description", ""),
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "comment": user_comment,
            "stages_rerun": affected,
        })

        # --- Requirement version tracking (AC-P2-01) -------------------------
        # Create a new CURRENT RequirementVersion for this applied change and
        # mark the previous CURRENT version as SUPERSEDED.
        #
        # Content convention:
        #   First version  → content = original_request (the project's base text).
        #   Later versions → content = previous content + appended change delta.
        # This is the most accurate representation available in the current data
        # flow: ChangeManager only receives a change description, not a full
        # rewritten requirement text.  The content field therefore accumulates
        # over time.  Wiring in a richer "full updated text" is a later task.
        req_version_updates = self._create_requirement_version(
            project_id=project_id,
            pj=pj,
            change_description=pending.get("description", ""),
        )
        # --- End requirement version tracking --------------------------------

        # --- Sprint plan staleness (AC-P2 sprint stale wiring) ---------------
        # Mark the sprint plan stale when code stages are affected so that the
        # REPLANNING phase knows which plan needs regenerating.  Non-fatal.
        sprint_plan_updates = self._update_sprint_plan_staleness(
            pj=pj,
            affected_stages=affected,
            new_version_id=req_version_updates.get("current_requirement_version_id"),
        )
        # --- End sprint plan staleness ---------------------------------------

        self._workspace.update_project_json(project_id, {
            "stages_completed": safe_stages,
            "pending_change": None,
            "requirement_changes": changes,
            "current_stage": affected[0] if affected else None,
            **req_version_updates,
            **sprint_plan_updates,
        })
        self._transition(project_id, ProjectState.RESUMING_FROM_CHANGE)

        logger.info(
            "Requirement change applied for %s: removed %d stages, resuming from %s",
            project_id, len(affected), affected[0] if affected else "end",
        )
        return {
            "status": "applied",
            "stages_removed": affected,
            "stages_kept": safe_stages,
            "resuming_from": affected[0] if affected else None,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_requirement_version(
        self,
        project_id: str,
        pj: dict,
        change_description: str,
    ) -> dict:
        """Create a new CURRENT RequirementVersion and supersede the previous one.

        Returns a dict of project.json keys to merge (requirement_versions,
        current_requirement_version_id).  Never raises — on any unexpected
        error it logs a warning and returns an empty dict so the rest of
        apply() is not blocked.

        Content convention (documented limitation):
            First version  → content = project.json["original_request"].
            Later versions → content = previous version content + change delta.
        ChangeManager only receives a change description, not a full rewritten
        requirement text, so content accumulates rather than being replaced.
        """
        from ..shared.models.requirement_version import RequirementVersion
        from ..shared.enums.requirement_version_status import RequirementVersionStatus

        try:
            stored_versions: list[dict] = list(pj.get("requirement_versions", []))
            current_version_id: str | None = pj.get("current_requirement_version_id")

            # ── Determine content for the new version ────────────────────────
            if current_version_id:
                # Find the previous CURRENT version to chain from
                prev_dict = next(
                    (v for v in stored_versions if v.get("version_id") == current_version_id),
                    None,
                )
                prev_content = prev_dict.get("content", "") if prev_dict else (
                    pj.get("original_request", "") or change_description
                )
                new_content = (
                    f"{prev_content}\n\n## Change Applied\n{change_description}"
                    if prev_content else change_description
                )
            else:
                # First version — use the original project request as the base
                new_content = pj.get("original_request", "") or change_description

            # ── Create the new CURRENT version ───────────────────────────────
            new_version = RequirementVersion(
                project_id=project_id,
                content=new_content,
                change_description=change_description,
                supersedes=current_version_id,
                status=RequirementVersionStatus.CURRENT,
                created_by="user",  # human-initiated change via apply()
            )

            # ── Mark the previous CURRENT version as SUPERSEDED ───────────────
            updated_versions = [
                ({**v, "status": RequirementVersionStatus.SUPERSEDED.value}
                 if v.get("version_id") == current_version_id else v)
                for v in stored_versions
            ]
            updated_versions.append(new_version.to_dict())

            logger.info(
                "RequirementVersion created: project=%s version_id=%s supersedes=%s",
                project_id, new_version.version_id, new_version.supersedes,
            )
            return {
                "requirement_versions": updated_versions,
                "current_requirement_version_id": new_version.version_id,
            }

        except Exception as exc:
            logger.warning(
                "RequirementVersion creation failed (non-fatal): project=%s error=%s",
                project_id, exc,
            )
            return {}

    def _update_sprint_plan_staleness(
        self,
        pj: dict,
        affected_stages: list[str],
        new_version_id: str | None,
    ) -> dict:
        """Mark sprint_plan as stale when code stages are among the affected stages.

        Returns a dict of project.json keys to merge — either
        ``{"sprint_plan": <updated dict>}`` or ``{}`` (no change needed).

        Conditions:
          - No sprint_plan in project.json → return {} (nothing to mark).
          - No code stage in affected_stages → return {} (plan is unaffected).
          - Otherwise → set stale=True and requirement_version_id on the plan dict.

        Non-fatal: any unexpected error is logged and {} is returned so the
        rest of apply() is not blocked.
        """
        try:
            sprint_plan_data = pj.get("sprint_plan")
            if not sprint_plan_data:
                return {}  # sprint planner has not run yet — nothing to mark

            if not set(affected_stages).intersection(_CODE_STAGES):
                return {}  # change does not touch sprint execution stages

            updated = dict(sprint_plan_data)
            updated["stale"] = True
            updated["requirement_version_id"] = new_version_id
            logger.info(
                "SprintPlan marked stale: project=%s requirement_version_id=%s",
                pj.get("project_id", "?"),
                new_version_id,
            )
            return {"sprint_plan": updated}

        except Exception as exc:
            logger.warning(
                "SprintPlan stale update failed (non-fatal): error=%s", exc,
            )
            return {}
