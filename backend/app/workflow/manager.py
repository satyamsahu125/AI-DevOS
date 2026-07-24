from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..shared.dto.pipeline_result import PipelineResult
from ..shared.dto.workflow_result import WorkflowResult
from ..workspace.manager import WorkspaceManager
from .dependency_graph import DependencyGraph
from .engine import WorkflowEngine
from .execution_state import ExecutionStateRegistry

logger = logging.getLogger(__name__)


class WorkflowManager:
    """Public entry point for running the workflow: the full multi-stage pipeline (run())
    or a single named stage for debugging (run_stage())."""

    def __init__(
        self,
        engine: WorkflowEngine | None = None,
        workspace_manager: WorkspaceManager | None = None,
        execution_state: ExecutionStateRegistry | None = None,
    ) -> None:
        """Wire the WorkflowEngine used to run stages, the WorkspaceManager used to detect
        already-completed stages so run() can resume instead of restarting from scratch, and the
        ExecutionStateRegistry used to report real "is this actually running right now" status
        and to support a real Stop button (see run_stage())."""
        self.engine = engine or WorkflowEngine()
        self.workspace_manager = workspace_manager or WorkspaceManager()
        self.execution_state = execution_state or ExecutionStateRegistry()

    def run(self, project_id: str, request: str) -> PipelineResult:
        """Run every not-yet-completed stage in DependencyGraph.STAGE_ORDER, in order.

        Reads project_id's persisted workspace state first and skips any
        stage already in stages_completed -- this makes run() resumable:
        if a previous /workflow/start call died mid-pipeline (backend
        restart, crashed process, dropped connection), calling it again
        continues from the first incomplete stage instead of re-running
        (and re-billing) every stage from strategic_review onward.

        Every stage after the first still receives `request` as its literal
        input string -- WorkflowEngine.run() itself prepends the previous
        stage's approved AgentMessage (namespaced by project_id, see
        _with_predecessor_message in workflow/engine.py) before calling the
        agent, so re-deriving that same predecessor text here would just
        duplicate it in the prompt. Stops and reports failure at the first
        stage that exhausts its retries.
        """
        started_at = datetime.now(timezone.utc)
        workspace_state = self.workspace_manager.load_project_json(project_id) or {}
        already_completed = set(workspace_state.get("stages_completed", []))
        completed_stages: list[str] = list(already_completed)
        failed_stage_name: str | None = None
        was_stopped = False
        last_message = "Pipeline did not run"

        for stage in DependencyGraph.ordered_stages():
            if stage.value in already_completed:
                logger.info("pipeline skipping already-completed stage: project_id=%s stage=%s", project_id, stage.value)
                continue
            logger.info("pipeline starting stage: project_id=%s stage=%s", project_id, stage.value)
            result = self.run_stage(project_id, stage.value, request)
            last_message = result.message

            if getattr(result, "stopped", False):
                was_stopped = True
                logger.info("pipeline stopped by user: project_id=%s stage=%s", project_id, stage.value)
                break
            if result.success:
                completed_stages.append(stage.value)
                logger.info("pipeline stage completed: project_id=%s stage=%s", project_id, stage.value)
            else:
                failed_stage_name = stage.value
                logger.error("pipeline stage failed after max retries: project_id=%s stage=%s", project_id, stage.value)
                break

        all_complete = failed_stage_name is None and not was_stopped
        if was_stopped:
            message = "Pipeline stopped by user"
        elif all_complete:
            message = "Pipeline complete"
        else:
            message = f"Pipeline failed at {failed_stage_name}: {last_message}"
        return PipelineResult(
            project_id=project_id,
            completed_stages=completed_stages,
            failed_stage=failed_stage_name,
            success=all_complete,
            message=message,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            stopped=was_stopped,
        )

    def run_stage(self, project_id: str, stage_name: str, content: str) -> WorkflowResult:
        """Run stage_name with content for project_id through the WorkflowEngine, tracking real
        in-flight status in execution_state for the duration of the call (see ExecutionStateRegistry) --
        this is what lets GET /workflow/{id} report genuine "running" status and what the Stop
        endpoint actually flags."""
        logger.info("workflow manager running: project_id=%s stage=%s", project_id, stage_name)
        self.execution_state.mark_running(project_id)
        self.workspace_manager.update_project_json(project_id, {"stopped": False})
        try:
            result = self.engine.run(project_id, stage_name, content)
        finally:
            self.execution_state.mark_stopped(project_id)
        if result.stopped:
            self.workspace_manager.update_project_json(project_id, {"stopped": True})
        return result
