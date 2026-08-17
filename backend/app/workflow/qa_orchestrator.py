"""QAOrchestrator — single responsibility: manage the Q&A clarification flow.

Extracted from WorkflowManager._handle_clarifying_state() and
WorkflowManager._handle_qa_flow().  WorkflowManager delegates to this
class whenever the project state is CLARIFYING, QA_PENDING, or QA_IN_PROGRESS.
"""
from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from ..shared.dto.pipeline_result import PipelineResult
from ..shared.enums.project_state import ProjectState
from ..shared.enums.stage import Stage

logger = logging.getLogger(__name__)


class QAOrchestrator:
    """Manages Q&A question generation, answer processing, and synthesis.

    Parameters
    ----------
    workspace_manager:
        Reads/writes project state, QA sessions, and project.json.
    artifact_manager:
        Saves ClarificationArtifact and DomainResearch artifacts.
    broadcaster:
        WebSocket status pusher.
    agent_factory:
        Creates the ClarificationAgent.
    pipeline_supervisor:
        Called after Q&A completes to continue the pipeline.
    execution_state:
        Marks pipeline as running/stopped for the resumed pipeline segment.
    run_stage_fn:
        callable(project_id, stage_name, content) → WorkflowResult
    transition_fn:
        callable(project_id, new_state) → None
    domain_researcher:
        Optional — if present, runs domain research before Q&A generation.
    engine:
        WorkflowEngine — provides get_workflow_state for reading from EventStore.
    """

    def __init__(
        self,
        workspace_manager: Any,
        artifact_manager: Any,
        broadcaster: Any,
        agent_factory: Any,
        pipeline_supervisor: Any,
        execution_state: Any,
        run_stage_fn: Any,          # callable(project_id, stage_name, content) → WorkflowResult
        transition_fn: Any,         # callable(project_id, new_state) → None
        domain_researcher: Any = None,
        engine: Any = None,
    ) -> None:
        self._workspace = workspace_manager
        self._artifact_manager = artifact_manager
        self._broadcaster = broadcaster
        self._agent_factory = agent_factory
        self._pipeline_supervisor = pipeline_supervisor
        self._execution_state = execution_state
        self._run_stage = run_stage_fn
        self._transition = transition_fn
        self._domain_researcher = domain_researcher
        self._engine = engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def handle_clarifying(
        self, project_id: str, request: str, skip_qa: bool,
    ) -> PipelineResult:
        """Entry point for CLARIFYING state."""
        if skip_qa:
            return self._skip_qa_path(project_id, request)
        return self._full_qa_path(project_id, request)

    def handle_qa_flow(self, project_id: str, request: str) -> PipelineResult:
        """Entry point for QA_PENDING / QA_IN_PROGRESS states."""
        state = self._workspace.get_state(project_id)

        if state == ProjectState.QA_PENDING:
            qa = self._workspace.get_qa_session(project_id)
            answered = len(qa.get("answers", []))
            total = len(qa.get("questions", []))
            if total > 0 and answered < total:
                # Use engine's get_workflow_state which reads from EventStore with fallback to workflow.json
                data = self._engine.get_workflow_state(project_id) if self._engine else (self._workspace.load_project_json(project_id) or {})
                return PipelineResult(
                    project_id=project_id,
                    state=ProjectState.QA_PENDING,
                    requires_user_action=True,
                    action_needed="answer_questions",
                    message=f"Answered {answered}/{total} questions. Please answer remaining questions.",
                    completed_stages=list(data.get("stages_completed", [])),
                )
            # All answered — advance to synthesis.
            self._transition(project_id, ProjectState.QA_IN_PROGRESS)
            state = ProjectState.QA_IN_PROGRESS

        if state == ProjectState.QA_IN_PROGRESS:
            return self._synthesise_qa(project_id, request)

        data = self._engine.get_workflow_state(project_id) if self._engine else (self._workspace.load_project_json(project_id) or {})
        return PipelineResult(
            project_id=project_id,
            state=state,
            success=False,
            message="Unexpected state in QA flow",
            completed_stages=list(data.get("stages_completed", [])),
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _skip_qa_path(self, project_id: str, request: str) -> PipelineResult:
        """Run StrategicReview directly, bypassing Q&A."""
        result = self._run_stage(project_id, "StrategicReview", request)
        if result.success:
            self._transition(project_id, ProjectState.REQUIREMENTS_READY)
            return self._pipeline_supervisor.run(project_id, request)
        return self._fail(project_id, "StrategicReview", result)

    def _full_qa_path(self, project_id: str, request: str) -> PipelineResult:
        """Run domain research → generate Q&A questions."""
        from ..agents.clarification import ClarificationAgent

        max_retries = 3
        questions: list = []
        for attempt in range(max_retries):
            try:
                self._broadcaster.status_update(
                    project_id=project_id,
                    state=ProjectState.CLARIFYING.value,
                    current_stage="Clarifying",
                )
                self._broadcaster.log_line(
                    project_id, "DomainResearch",
                    f"Attempt {attempt + 1}/{max_retries}: Running domain research...",
                )
                domain_brief = self._run_domain_research(project_id, request)

                self._broadcaster.log_line(
                    project_id, "Clarifying",
                    f"Attempt {attempt + 1}/{max_retries}: Generating clarification questions...",
                )
                agent = self._agent_factory.create("clarification")
                if isinstance(agent, ClarificationAgent):
                    q_set = agent.generate_questions(request, domain_brief=domain_brief)
                    questions = [
                        q.model_dump(mode="json") if hasattr(q, "model_dump") else q
                        for q in q_set.questions
                    ]
                    if questions:
                        break
            except Exception as exc:
                logger.warning(
                    "Clarification generation failed on attempt %d: %s", attempt + 1, exc,
                )
                if attempt == max_retries - 1:
                    return self._fail(
                        project_id, "Clarifying",
                        SimpleNamespace(message=f"Failed to generate clarification questions: {exc}"),
                    )

        if questions:
            self._workspace.save_qa_questions(project_id, questions)
            self._transition(project_id, ProjectState.QA_PENDING)
            data = self._engine.get_workflow_state(project_id) if self._engine else (self._workspace.load_project_json(project_id) or {})
            return PipelineResult(
                project_id=project_id,
                state=ProjectState.QA_PENDING,
                requires_user_action=True,
                action_needed="answer_questions",
                message=f"I have {len(questions)} questions to help me understand your project better.",
                completed_stages=list(data.get("stages_completed", [])),
            )

        # No questions generated — bypass Q&A with minimal artifact.
        logger.warning(
            "QA bypassed for %s: no questions generated. Using minimal clarification.",
            project_id,
        )
        return self._bypass_qa_with_minimal_artifact(project_id, request)

    def _synthesise_qa(self, project_id: str, request: str) -> PipelineResult:
        """Synthesise Q&A answers into ClarificationArtifact, then run StrategicReview."""
        from ..agents.clarification import ClarificationAgent

        self._broadcaster.status_update(
            project_id=project_id,
            state=ProjectState.QA_IN_PROGRESS.value,
            current_stage="Synthesizing Requirements",
        )
        self._broadcaster.log_line(
            project_id, "Clarifying",
            "Synthesizing requirements from Q&A session...",
        )

        agent = self._agent_factory.create("clarification")
        qa = self._workspace.get_qa_session(project_id)
        clarification_struct: dict = {}
        if isinstance(agent, ClarificationAgent):
            artifact_obj = agent.process_answers(request, qa)
            clarification_struct = (
                artifact_obj.model_dump(mode="json")
                if hasattr(artifact_obj, "model_dump") else {}
            )

        self._artifact_manager.save_artifact(
            project_id=project_id,
            stage=Stage.Clarification,
            content=json.dumps(clarification_struct, indent=2),
            structured_content=clarification_struct,
        )
        self._record_to_memory_orchestrator(project_id, Stage.Clarification, clarification_struct)
        self._workspace.mark_qa_complete(project_id)

        # Build StrategicReview context.
        domain_artifact = self._artifact_manager.get_artifact(project_id, Stage.DomainResearch)
        domain_struct = (
            getattr(domain_artifact, "structured_content", None) or {}
            if domain_artifact else {}
        )
        strategic_context = json.dumps({
            "original_request": request,
            "clarification": clarification_struct,
            "domain_research": domain_struct,
        }, indent=2)

        strategic_result = self._run_stage(project_id, "StrategicReview", strategic_context)
        if not strategic_result.success:
            logger.warning(
                "StrategicReview failed after Q&A for %s: %s — continuing anyway",
                project_id, strategic_result.message,
            )

        # Ensure contiguous prefix in stages_completed.
        qa_data = self._engine.get_workflow_state(project_id) if self._engine else (self._workspace.load_project_json(project_id) or {})
        completed = list(qa_data.get("stages_completed", []))
        for stage_val in (Stage.Clarification.value, Stage.StrategicReview.value):
            if stage_val not in completed:
                completed.insert(0, stage_val)
        self._workspace.update_project_json(project_id, {"stages_completed": completed})

        self._transition(project_id, ProjectState.REQUIREMENTS_READY)

        # Do NOT call mark_running / mark_stopped here.  The outer
        # WorkflowManager.run() already holds the running lock for the full
        # workflow invocation (counter = 1, stop_requested cleared).  A second
        # mark_running call here increments the counter to 2, which means any
        # stop request received during Q&A is NOT cleared by this inner call,
        # and the finally-block mark_stopped only decrements to 1 — leaving the
        # project appearing "still running" until WorkflowManager.run() returns.
        return self._pipeline_supervisor.run(project_id, request)

    def _bypass_qa_with_minimal_artifact(
        self, project_id: str, request: str,
    ) -> PipelineResult:
        minimal = {
            "original_request": request,
            "project_description": request,
            "functional_requirements": [],
            "non_functional_requirements": [],
            "scale_profile": {
                "user_count": "unknown",
                "auth_needed": False,
                "database_needed": False,
                "infrastructure_tier": "unknown",
            },
            "explicit_non_requirements": [],
            "open_questions": [],
            "inferred_scope": (
                "QA bypassed — question generation returned no questions. "
                "Infer full scope from the original request only."
            ),
        }
        self._artifact_manager.save_artifact(
            project_id=project_id,
            stage=Stage.Clarification,
            content=json.dumps(minimal, indent=2),
            structured_content=minimal,
        )
        self._record_to_memory_orchestrator(project_id, Stage.Clarification, minimal)
        result = self._run_stage(project_id, "StrategicReview", request)
        if result.success:
            self._transition(project_id, ProjectState.REQUIREMENTS_READY)
            return self._pipeline_supervisor.run(project_id, request)
        return self._fail(project_id, "StrategicReview", result)

    def _run_domain_research(self, project_id: str, request: str) -> dict | None:
        if self._domain_researcher is None:
            return None
        try:
            brief = self._domain_researcher.research(request)
            brief_dict = brief.model_dump(mode="json") if hasattr(brief, "model_dump") else {}
            self._artifact_manager.save_artifact(
                project_id=project_id,
                stage=Stage.DomainResearch,
                content=str(brief_dict),
                structured_content=brief_dict,
            )
            return brief_dict
        except Exception as exc:
            logger.warning("Domain research failed (non-fatal): %s", exc)
            return None

    def _record_to_memory_orchestrator(
        self, project_id: str, stage: Stage, struct: dict,
    ) -> None:
        """Write approved stage output to MemoryOrchestrator if available."""
        try:
            # Access memory_orchestrator through the engine if possible.
            engine = getattr(self._pipeline_supervisor, "engine", None)
            mo = getattr(engine, "memory_orchestrator", None)
            if mo is not None:
                mo.record_approval(project_id, stage, struct)
        except Exception as exc:
            logger.debug("_record_to_memory_orchestrator failed (non-fatal): %s", exc)

    def _fail(self, project_id: str, stage_label: str, result: Any) -> PipelineResult:
        self._transition(project_id, ProjectState.FAILED)
        self._workspace.update_project_json(
            project_id, {"failed_at_stage": stage_label, "failure_reason": result.message},
        )
        data = self._engine.get_workflow_state(project_id) if self._engine else (self._workspace.load_project_json(project_id) or {})
        return PipelineResult(
            project_id=project_id,
            state=ProjectState.FAILED,
            success=False,
            message=f"Pipeline failed at {stage_label}: {result.message}",
            failed_stage=stage_label,
            completed_stages=list(data.get("stages_completed", [])),
        )
