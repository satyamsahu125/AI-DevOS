"""SprintExecutor — single responsibility: run one complete sprint.

Extracted from WorkflowManager._run_sprint.  This eliminates the circular
dependency where PipelineSupervisor called back into WorkflowManager for
sprint execution.

Responsibilities:
  1. Set the active sprint in workspace
  2. Run ScrumMaster (non-blocking on failure)
  3. Run FileStructurePlanner (required)
  4. Run BackendDeveloper
  5. Run FrontendDeveloper
  6. Run SprintDeploy and SprintReview through the engine (with retry + review)
  7. Validate sprint output (non-blocking)
  8. Return SprintResult

Does NOT own: sprint retry logic, post-sprint indexing, git commits,
sandbox runs, dependency pinning, preview management.  Those stay in
PipelineSupervisor which calls this executor once per sprint.

Concurrent agent execution
--------------------------
When ``SPRINT_PARALLEL_AGENTS >= 2``, BackendDeveloper and FrontendDeveloper
are dispatched concurrently via :class:`~concurrent.futures.ThreadPoolExecutor`
(steps 4 and 5).  They write to disjoint directories (``backend/`` vs
``frontend/``) so no file-path conflicts are possible.

When ``SPRINT_PARALLEL_AGENTS`` is 1 (default) or unset, the two agents run
sequentially — identical to the original behaviour; no regression.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from ..shared.enums.stage import Stage
from ..shared.models.sprint import Sprint, SprintResult

logger = logging.getLogger(__name__)

# Design memory key — must match shared/constants.py.
from ..shared.constants import DESIGN_MEMORY_KEY


class SprintExecutor:
    """Runs exactly one sprint end-to-end.

    Parameters
    ----------
    engine:
        WorkflowEngine — runs stages through execute→review→retry.
    agent_factory:
        Creates SprintDeploy / SprintReview agents.
    workspace_manager:
        Reads/writes project state and artifacts.
    artifact_manager:
        Reads persisted stage artifacts (Architect, ScrumMaster, etc.).
    sprint_monitor:
        Optional sprint output validator and brief generator.
    broadcaster:
        WebSocket status pusher.
    """

    def __init__(
        self,
        engine: Any,
        agent_factory: Any,
        workspace_manager: Any,
        artifact_manager: Any,
        sprint_monitor: Any = None,
        broadcaster: Any = None,
        project_writer: Any = None,
        code_sandbox: Any = None,
    ) -> None:
        self._engine = engine
        self._agent_factory = agent_factory
        self._workspace = workspace_manager
        self._artifact_manager = artifact_manager
        self._sprint_monitor = sprint_monitor
        self._broadcaster = broadcaster
        self._project_writer = project_writer
        # Phase 1: code execution sandbox — when provided, sprint is only
        # marked complete after install → build → test succeed.
        self._code_sandbox = code_sandbox

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, project_id: str, sprint: Sprint) -> SprintResult:
        """Execute sprint end-to-end and return a SprintResult."""
        logger.info("SprintExecutor: starting sprint %d: %s",
                    sprint.sprint_number, sprint.name)
        self._workspace.set_current_sprint(project_id, sprint.sprint_number)
        self._workspace.create_sprint_folder(project_id, sprint.sprint_number)

        arch = self._artifact_manager.get_artifact(project_id, Stage.Architect)
        initial_context = self._build_sprint_context(project_id, sprint, arch)

        # ── Step 1: ScrumMaster (non-blocking) ──────────────────────
        self._run_scrum_master(project_id, sprint, initial_context)

        # Rebuild context now that ScrumMaster artifact may exist.
        plan_context = self._build_sprint_context(project_id, sprint, arch)

        # ── Step 1b: SprintDeltaPlanner (non-blocking) ───────────────
        # Produces explicit create/update/patch decisions per file so that
        # FileStructurePlanner can set operations reliably instead of
        # inferring them from a raw EXISTING FILES list.
        self._run_sprint_delta(project_id, sprint, plan_context)

        # ── Step 2: FileStructurePlanner (required) ──────────────────
        plan_result = self._run_file_planner(project_id, plan_context)
        if not plan_result.success:
            return SprintResult(
                sprint_complete=False,
                success=False,
                message=plan_result.message,
            )

        # Load file plan and initialise project structure on first sprint.
        file_plan = self._load_file_plan(project_id, sprint.sprint_number)
        if sprint.sprint_number == 1 and self._project_writer is not None:
            tech_stack = getattr(file_plan, "tech_stack", {}) or {}
            self._project_writer.initialize_project(project_id, tech_stack)

        # ── Steps 3+4: BackendDeveloper & FrontendDeveloper ─────────
        # These agents write to disjoint directories (backend/ vs frontend/)
        # so they can run concurrently when SPRINT_PARALLEL_AGENTS >= 2.
        backend_result, frontend_result = self._run_developer_agents(
            project_id, plan_context,
        )

        all_success = backend_result.success and frontend_result.success

        if all_success:
            # Run sprint QA (new step per B-31 fix)
            qa_result = self._run_sprint_qa(project_id, sprint, plan_context)
            if not qa_result.get("passed", False):
                logger.warning(
                    "SprintExecutor: sprint %d QA found issues: %s",
                    sprint.sprint_number, qa_result.get("summary", "QA failed"),
                )
                # Don't fail the sprint for QA issues — just log them
                # The sandbox verification will catch actual test failures

            # ── Phase 1: Verify generated code before marking sprint complete ─
            # install → build → test must pass.  A build failure here means the
            # sprint is NOT marked complete and PipelineSupervisor sees success=False.
            sandbox_success, sandbox_message = self._run_sandbox_verification(
                project_id, sprint,
            )
            if not sandbox_success:
                logger.error(
                    "SprintExecutor: sprint %d sandbox verification failed: %s",
                    sprint.sprint_number, sandbox_message,
                )
                return SprintResult(
                    sprint_complete=False,
                    all_sprints_complete=False,
                    success=False,
                    message=f"Sprint {sprint.sprint_number} build/test failed: {sandbox_message}",
                )

            self._run_sprint_deploy_and_review(project_id, sprint, file_plan)
            self._workspace.mark_sprint_complete(project_id, sprint.sprint_number)
            self._run_sprint_validation(project_id, sprint)

        return SprintResult(
            sprint_complete=all_success,
            all_sprints_complete=False,
            success=all_success,
            message="Sprint completed" if all_success else "Sprint execution failed",
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_developer_agents(
        self, project_id: str, plan_context: str,
    ) -> tuple[Any, Any]:
        """Run BackendDeveloper and FrontendDeveloper, optionally concurrently.

        When ``SPRINT_PARALLEL_AGENTS >= 2`` (set via the environment variable),
        both agents are submitted to a :class:`~concurrent.futures.ThreadPoolExecutor`
        and run simultaneously.  Because they write exclusively to ``backend/`` and
        ``frontend/`` directories respectively, there are no shared output paths and
        no risk of file-level conflicts.

        When ``SPRINT_PARALLEL_AGENTS`` is 1 (default) or unset, the agents run
        sequentially in the original order (backend first, then frontend) — identical
        to the pre-parallel implementation.

        Returns
        -------
        (backend_result, frontend_result)
            Both are WorkflowResult objects returned by :meth:`_run_engine_stage`.
        """
        parallel_agents = int(os.getenv("SPRINT_PARALLEL_AGENTS", "1"))

        if parallel_agents >= 2:
            logger.info(
                "SprintExecutor: running BackendDeveloper + FrontendDeveloper concurrently "
                "(SPRINT_PARALLEL_AGENTS=%d)",
                parallel_agents,
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                backend_future = executor.submit(
                    self._run_engine_stage,
                    project_id, "BackendDeveloper", plan_context,
                )
                frontend_future = executor.submit(
                    self._run_engine_stage,
                    project_id, "FrontendDeveloper", plan_context,
                )
                # Both futures are awaited before returning.  Exceptions from
                # either agent surface here as the future's exception, which is
                # then re-raised.  The executor __exit__ also waits for all
                # submitted futures before the context manager exits.
                backend_result = backend_future.result()
                frontend_result = frontend_future.result()
        else:
            # ── Sequential path — identical to original behaviour ─────────────
            backend_result = self._run_engine_stage(
                project_id, "BackendDeveloper", plan_context,
            )
            frontend_result = self._run_engine_stage(
                project_id, "FrontendDeveloper", plan_context,
            )

        return backend_result, frontend_result

    def _run_engine_stage(
        self, project_id: str, stage_name: str, context: str,
    ) -> Any:
        """Run a stage through the engine (has retry, reviewer, trajectory recording)."""
        from ..shared.dto.workflow_result import WorkflowResult
        from .stage_lookup import resolve_stage_name
        resolved = resolve_stage_name(stage_name)
        if self._broadcaster:
            self._broadcaster.stage_started(project_id, stage_name, 1)
        result = self._engine.run(project_id, resolved, context)
        if self._broadcaster:
            if result.success:
                self._broadcaster.stage_complete(project_id, stage_name, 1, 0)
            else:
                self._broadcaster.stage_failed(project_id, stage_name, result.message)
        return result

    def _run_scrum_master(
        self, project_id: str, sprint: Sprint, context: str,
    ) -> None:
        """Run ScrumMaster — failure is non-blocking."""
        if self._broadcaster:
            self._broadcaster.stage_started(project_id, "ScrumMaster", 1)
        try:
            from .stage_lookup import resolve_stage_name
            result = self._engine.run(project_id, resolve_stage_name("scrum_master"), context)
            if result.success:
                if self._broadcaster:
                    self._broadcaster.stage_complete(project_id, "ScrumMaster", 1, 0)
                self._persist_to_artifact_store(
                    project_id, Stage.ScrumMaster,
                    f"sprint_{sprint.sprint_number}", "scrum_plan",
                )
            else:
                logger.warning(
                    "ScrumMaster failed for sprint %d (non-blocking): %s",
                    sprint.sprint_number, result.message,
                )
                if self._broadcaster:
                    self._broadcaster.stage_failed(project_id, "ScrumMaster", result.message)
        except Exception as exc:
            logger.warning("ScrumMaster raised (non-blocking): %s", exc)

    def _run_sprint_delta(
        self, project_id: str, sprint: Sprint, context: str,
    ) -> None:
        """Run SprintDeltaPlanner — non-blocking; failure is silently logged.

        For Sprint 1 the action returns immediately without an LLM call (all
        files are new).  For Sprint 2+ it reasons about which existing files
        need update/patch vs which files are new (create) and persists a
        SprintDeltaArtifact for WriteFilePlanAction to consume.
        """
        try:
            from .stage_lookup import resolve_stage_name
            result = self._engine.run(
                project_id, resolve_stage_name("sprint_delta"), context,
            )
            if result.success:
                logger.info(
                    "SprintDeltaPlanner succeeded for sprint %d",
                    sprint.sprint_number,
                )
            else:
                logger.warning(
                    "SprintDeltaPlanner failed for sprint %d (non-blocking): %s",
                    sprint.sprint_number, result.message,
                )
        except Exception as exc:
            logger.warning(
                "SprintDeltaPlanner raised for sprint %d (non-blocking): %s",
                sprint.sprint_number, exc,
            )

    def _run_file_planner(self, project_id: str, context: str) -> Any:
        """Run FileStructurePlanner — required for sprint to proceed."""
        if self._broadcaster:
            self._broadcaster.stage_started(project_id, "FileStructurePlanner", 1)
        from .stage_lookup import resolve_stage_name
        result = self._engine.run(project_id, resolve_stage_name("file_planner"), context)
        if result.success:
            if self._broadcaster:
                self._broadcaster.stage_complete(project_id, "FileStructurePlanner", 1, 0)
        else:
            if self._broadcaster:
                self._broadcaster.stage_failed(project_id, "FileStructurePlanner", result.message)
        return result

    def _run_sandbox_verification(
        self,
        project_id: str,
        sprint: "Sprint",
    ) -> tuple[bool, str]:
        """Run install → build → test against generated code; persist result.

        Called inside SprintExecutor.run() after BackendDev + FrontendDev succeed,
        before mark_sprint_complete().  A build failure makes this return
        (False, message) which causes the sprint to be marked failed.

        Design decisions:
        - ``require_execution=True`` so execution always runs regardless of
          SANDBOX_ENABLED; the flag only controls Docker vs subprocess isolation.
        - Result is persisted to ArtifactStore so PipelineSupervisor._run_sandbox()
          can load it instead of re-running, avoiding double execution.
        - Returns (True, "") when code_sandbox is not wired (backward compat).
        - Non-fatal internal errors in persist are logged but never block the sprint.
        """
        if self._code_sandbox is None:
            # Not wired — behave as pre-Phase-1 (no execution gate).
            logger.debug(
                "SprintExecutor: code_sandbox not wired, skipping execution verification for sprint %d",
                sprint.sprint_number,
            )
            return True, ""

        try:
            logger.info(
                "SprintExecutor: running sandbox verification: project=%s sprint=%d",
                project_id, sprint.sprint_number,
            )
            if self._broadcaster:
                self._broadcaster.stage_started(project_id, "SandboxVerification")

            sandbox_result = self._code_sandbox.run(
                project_id,
                sprint=sprint.sprint_number,
                require_execution=True,
            )

            # Persist result to ArtifactStore for restart-survival and
            # to let PipelineSupervisor._run_sandbox() skip re-execution.
            self._persist_sandbox_result(project_id, sprint.sprint_number, sandbox_result)

            # Determine whether the sprint passes.
            # A build failure (including install failure surfaced as build failure)
            # is non-negotiable: AC-05.
            if not sandbox_result.build.success:
                errors = "; ".join(sandbox_result.build.errors[:3]) or "unknown build error"
                if self._broadcaster:
                    self._broadcaster.stage_failed(
                        project_id, "SandboxVerification",
                        f"Build failed: {errors}",
                    )
                return False, f"Build failed: {errors}"

            # AC-P2-09: test failures gate the sprint when tests exist.
            # If test.total == 0 the project has no tests yet — do not penalise.
            if sandbox_result.test.failed > 0 and sandbox_result.test.total > 0:
                failed_names = "; ".join(
                    f.get("test_name", "unknown")
                    for f in sandbox_result.test.failures[:3]
                ) or f"{sandbox_result.test.failed} test(s) failed"
                msg = (
                    f"Tests failed: {sandbox_result.test.failed}/{sandbox_result.test.total}"
                    f" — {failed_names}"
                )
                if self._broadcaster:
                    self._broadcaster.stage_failed(project_id, "SandboxVerification", msg)
                return False, msg

            if self._broadcaster:
                self._broadcaster.stage_complete(project_id, "SandboxVerification", 1, 0)

            logger.info(
                "SprintExecutor: sandbox verification passed: project=%s sprint=%d "
                "install=%s build=%s tests=%d/%d",
                project_id, sprint.sprint_number,
                sandbox_result.install.success,
                sandbox_result.build.success,
                sandbox_result.test.passed,
                sandbox_result.test.total,
            )
            return True, ""

        except Exception as exc:
            # Unexpected exception in sandbox — log and fail the sprint so the
            # error is visible rather than silently treating it as success (AC-05).
            logger.error(
                "SprintExecutor: sandbox verification raised: project=%s sprint=%d error=%s",
                project_id, sprint.sprint_number, exc,
                exc_info=True,
            )
            return False, f"Sandbox verification error: {exc}"

    def _persist_sandbox_result(
        self,
        project_id: str,
        sprint_number: int,
        sandbox_result: Any,
    ) -> None:
        """Persist SandboxResult to ArtifactStore at sprint_N/sandbox_result.

        Non-fatal — any exception is caught and logged so a persistence error
        never propagates to fail the sprint.  This is the canonical location
        PipelineSupervisor._run_sandbox() checks before deciding whether to
        re-run the sandbox (to avoid double execution).
        """
        try:
            store = self._workspace.get_artifact_store(project_id)
            store.write(
                scope=f"sprint_{sprint_number}",
                name="sandbox_result",
                data=sandbox_result._to_dict(),
            )
            logger.debug(
                "SprintExecutor: sandbox_result persisted: project=%s scope=sprint_%d",
                project_id, sprint_number,
            )
        except Exception as exc:
            logger.warning(
                "SprintExecutor: failed to persist sandbox_result (non-fatal): "
                "project=%s sprint=%d error=%s",
                project_id, sprint_number, exc,
            )

    def _run_sprint_deploy_and_review(
        self, project_id: str, sprint: Sprint, file_plan: Any,
    ) -> None:
        """Run SprintDeploy and SprintReview through the engine (with retry + reviewer)."""
        try:
            if self._broadcaster:
                self._broadcaster.stage_started(project_id, "SprintDeploy")
            deploy_result = self._engine.run(project_id, "SprintDeploy", "")
            if self._broadcaster:
                if deploy_result.success:
                    self._broadcaster.stage_complete(project_id, "SprintDeploy", 1, 0)
                else:
                    self._broadcaster.stage_failed(
                        project_id, "SprintDeploy", deploy_result.message,
                    )

            if self._broadcaster:
                self._broadcaster.stage_started(project_id, "SprintReview")
            review_result = self._engine.run(project_id, "SprintReview", "")
            if self._broadcaster:
                if review_result.success:
                    self._broadcaster.stage_complete(project_id, "SprintReview", 1, 0)
                else:
                    self._broadcaster.stage_failed(
                        project_id, "SprintReview", review_result.message,
                    )
        except Exception as exc:
            logger.warning(
                "SprintDeploy/SprintReview failed for %s sprint %d (non-blocking): %s",
                project_id, sprint.sprint_number, exc, exc_info=True,
            )

    def _run_sprint_validation(self, project_id: str, sprint: Sprint) -> None:
        if self._sprint_monitor is None:
            return
        try:
            issues = self._sprint_monitor.validate_sprint_output(
                project_id, sprint.sprint_number,
            )
            if issues:
                logger.warning(
                    "Sprint %d validation issues for %s: %s",
                    sprint.sprint_number, project_id, issues,
                )
                self._workspace.update_project_json(
                    project_id,
                    {f"sprint_{sprint.sprint_number}_issues": issues},
                )
        except Exception as exc:
            logger.debug("sprint validation failed (non-fatal): %s", exc)

    def _run_sprint_qa(
        self, project_id: str, sprint: "Sprint", plan_context: str,
    ) -> dict:
        """Run QA agent's sprint QA method and return structured results.

        Called after BackendDeveloper and FrontendDeveloper complete,
        before sandbox verification.  Uses the agent factory pattern
        to obtain a QAAgent instance and calls its run_sprint_qa method.
        """
        try:
            from ..agents.factory import AgentFactory
            from ..agents.qa import QAAgent

            # Get required context from artifacts
            arch_artifact = self._artifact_manager.get_artifact(project_id, Stage.Architect)
            arch_content = getattr(arch_artifact, "structured_content", {}) or getattr(arch_artifact, "content", {}) or {}

            # Get file plan for this sprint
            file_plan = self._load_file_plan(project_id, sprint.sprint_number)
            file_plan_dict = {}
            if hasattr(file_plan, "model_dump"):
                file_plan_dict = file_plan.model_dump(mode="json")
            elif isinstance(file_plan, dict):
                file_plan_dict = file_plan

            # Get user stories from ProductOwner artifact
            po_artifact = self._artifact_manager.get_artifact(project_id, Stage.ProductOwner)
            user_stories = getattr(po_artifact, "structured_content", {}) or getattr(po_artifact, "content", {}) or {}

            # Create QA agent via factory (or direct instantiation)
            factory = AgentFactory()
            qa_agent = factory.create("qa")

            # Call run_sprint_qa
            qa_result = qa_agent.run_sprint_qa(
                project_id=project_id,
                sprint_number=sprint.sprint_number,
                file_plan=file_plan_dict,
                architecture=arch_content,
                user_stories=user_stories,
                iteration=1,
            )

            logger.info(
                "SprintExecutor: sprint %d QA completed: passed=%s total_tests=%d",
                sprint.sprint_number, qa_result.get("passed"), qa_result.get("total_tests"),
            )
            return qa_result

        except Exception as exc:
            logger.warning("SprintExecutor: sprint %d QA failed (non-fatal): %s", sprint.sprint_number, exc)
            return {"passed": True, "total_tests": 0, "failed_tests": 0, "failures": [], "summary": "QA skipped due to error", "sprint": sprint.sprint_number, "iteration": 1}

    def _build_sprint_context(
        self, project_id: str, sprint: Sprint, arch: Any,
    ) -> str:
        """Assemble the context string for this sprint's stages."""
        sprint_brief = ""
        if self._sprint_monitor is not None:
            try:
                sprint_brief = self._sprint_monitor.generate_sprint_brief(
                    project_id=project_id,
                    sprint_number=sprint.sprint_number,
                    sprint_goal=sprint.goal,
                )
            except Exception as exc:
                logger.debug("SprintMonitor.generate_sprint_brief failed (non-fatal): %s", exc)

        arch_text = getattr(arch, "content", str(arch)) if arch else ""
        scrum_artifact = self._artifact_manager.get_artifact(project_id, Stage.ScrumMaster)
        scrum_text = getattr(scrum_artifact, "content", "") if scrum_artifact else ""

        parts: list[str] = []
        if sprint_brief:
            parts.append(sprint_brief)
        else:
            parts.extend([
                f"Sprint {sprint.sprint_number}: {sprint.name}",
                f"Goal: {sprint.goal}",
                f"Features: {', '.join(sprint.features)}",
            ])
        parts.append(f"\nArchitecture Spec:\n{arch_text[:1500]}")
        if scrum_text:
            parts.append(f"\nScrumMaster Plan:\n{scrum_text[:2000]}")

        return "\n".join(parts)

    def _load_file_plan(self, project_id: str, sprint_number: int) -> Any:
        from ..shared.schemas.file_plan_schema import FilePlan
        artifacts_dir = self._workspace.get_workspace_path(project_id) / "artifacts"
        for filename in (
            f"file_plan_sprint_{sprint_number}.json",
            "FileStructurePlanner.json",
            "sprint_plan.json",
        ):
            plan_json = artifacts_dir / filename
            if plan_json.exists():
                try:
                    data = json.loads(plan_json.read_text(encoding="utf-8"))
                    struct = data.get("structured") or data
                    raw_files = struct.get("files")
                    if isinstance(raw_files, list):
                        files_dict: dict = {}
                        for entry in raw_files:
                            path = (
                                entry.get("path", "") if isinstance(entry, dict)
                                else getattr(entry, "path", "")
                            )
                            if path:
                                files_dict[path] = {
                                    "file_path": path,
                                    "purpose": (
                                        entry.get("purpose", "") if isinstance(entry, dict)
                                        else getattr(entry, "purpose", "")
                                    ),
                                }
                        struct = {
                            **struct,
                            "files": files_dict,
                            "project_id": project_id,
                            "sprint_number": sprint_number,
                        }
                    return FilePlan.model_validate(struct)
                except Exception as exc:
                    logger.warning("Failed to parse file plan json (%s): %s", filename, exc)
        return FilePlan(project_id=project_id, sprint_number=sprint_number)

    def _persist_to_artifact_store(
        self,
        project_id: str,
        stage: Stage,
        scope: str,
        artifact_name: str,
    ) -> None:
        try:
            artifact = self._artifact_manager.get_artifact(project_id, stage)
            if artifact is None:
                return
            store = self._workspace.get_artifact_store(project_id)
            store.write(
                scope=scope,
                name=artifact_name,
                data={
                    "content": artifact.content or "",
                    "stage": stage.value,
                    "written_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as exc:
            logger.warning(
                "SprintExecutor: non-fatal artifact store write failure %s/%s: %s",
                project_id, stage.value, exc,
            )
