"""SprintSupervisor — per-sprint execution orchestrator with feedback loops.

Manages one sprint's complete execution including:
- Agent execution in dependency order (ScrumMaster → FilePlanner → Backend/Frontend → TechLead → QA → Deploy → Review)
- Feedback loops (TechLead rejections, QA failures)
- Retry gates (max_dev_review_iterations, max_qa_iterations, etc.)
- Escalation to SPRINT_BLOCKED when retry limits exceeded

The supervisor reads sprint artifacts from ArtifactStore and routes failures
to the right agent based on root cause analysis by BugAnalystAgent.

Retry counters are local to this run (not persisted). If the process restarts,
the sprint re-runs from step 1.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from types import SimpleNamespace

from ..agents.backend import BackendDeveloperAgent
from ..agents.bug_analyst import BugAnalystAgent
from ..agents.factory import AgentFactory
from ..agents.frontend import FrontendDeveloperAgent
from ..agents.qa import QAAgent
from ..agents.scrum_master import ScrumMasterAgent
from ..agents.sprint_deploy import SprintDeployAgent
from ..agents.sprint_review import SprintReviewAgent
from ..agents.tech_lead import TechLeadAgent
from ..llm.manager import LLMManager
from ..workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)


@dataclass
class SprintResult:
    """Result of a sprint execution."""
    success: bool
    blocked: bool = False
    message: str = ""


class SprintSupervisor:
    """Orchestrates one sprint's execution with feedback loops and retry gates.

    Parameters
    ----------
    workspace_manager:
        WorkspaceManager for reading/writing artifacts.
    llm_manager:
        LLMManager for LLM calls.
    settings:
        Settings object with sprint_retry config (retry limits).
    agent_factory:
        AgentFactory for agent instantiation. If None, uses default.
    """

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        llm_manager: LLMManager,
        settings: object,
        agent_factory: AgentFactory | None = None,
    ) -> None:
        self.workspace_manager = workspace_manager
        self.llm_manager = llm_manager
        self.settings = settings
        self.agent_factory = agent_factory or AgentFactory()

        # Extract retry limits from settings.
        sprint_retry = getattr(settings, "sprint_retry", None)
        if sprint_retry is None:
            # Fallback defaults if settings missing.
            self._max_dev_review_iterations = 3
            self._max_qa_iterations = 3
            self._max_spec_fix_iterations = 2
        else:
            self._max_dev_review_iterations = getattr(sprint_retry, "max_dev_review_iterations", 3)
            self._max_qa_iterations = getattr(sprint_retry, "max_qa_iterations", 3)
            self._max_spec_fix_iterations = getattr(sprint_retry, "max_spec_fix_iterations", 2)

    def run_sprint(
        self,
        project_id: str,
        sprint_number: int,
        request: str,
        user_request: object | None = None,
    ) -> SprintResult:
        """Execute one full sprint with feedback loops and retry gates.

        Parameters
        ----------
        project_id:
            Project identifier.
        sprint_number:
            Sprint number (1-indexed).
        request:
            User-facing request/context for this sprint.
        user_request:
            Optional user request object (passed to agents if needed).

        Returns
        -------
        SprintResult
            success=True if sprint completed successfully.
            success=False and blocked=True if retry limits exceeded.
            success=False and blocked=False if error occurred.
        """
        try:
            return self._run_sprint_impl(project_id, sprint_number, request, user_request)
        except Exception as exc:
            logger.error(
                "[SprintSupervisor] sprint %d failed with exception: %s",
                sprint_number,
                exc,
                exc_info=True,
            )
            return SprintResult(
                success=False,
                blocked=False,
                message=f"Sprint {sprint_number} failed: {exc}",
            )

    def _run_sprint_impl(
        self,
        project_id: str,
        sprint_number: int,
        request: str,
        user_request: object | None = None,
    ) -> SprintResult:
        """Internal sprint execution implementation."""
        logger.info(
            "[SprintSupervisor] starting sprint %d (project: %s)",
            sprint_number,
            project_id,
        )

        store = self.workspace_manager.get_artifact_store(project_id)
        scope = f"sprint_{sprint_number}"

        # ===================================================================
        # Step 1: ScrumMaster → tasks.json
        # ===================================================================
        logger.debug("[SprintSupervisor] step 1: ScrumMaster")
        scrum_master = ScrumMasterAgent(llm_manager=self.llm_manager)
        tasks_ctx = SimpleNamespace(content=request, project_id=project_id, sprint=sprint_number)
        tasks_artifact = scrum_master.execute(tasks_ctx)
        tasks_data = tasks_artifact.structured_content or {}
        store.write(scope, "tasks", {
            "content": tasks_artifact.content,
            "structured": tasks_data,
        })
        logger.debug("[SprintSupervisor] ScrumMaster: tasks created")

        # ===================================================================
        # Step 2: FilePlanner → file_plan.json
        # ===================================================================
        logger.debug("[SprintSupervisor] step 2: FilePlanner")
        file_planner = self.agent_factory.create("file_planner")
        file_plan_ctx = SimpleNamespace(
            content=request,
            project_id=project_id,
            sprint=sprint_number,
        )
        file_plan_artifact = file_planner.execute(file_plan_ctx)
        file_plan_data = file_plan_artifact.structured_content or {}
        store.write(scope, "file_plan", {
            "content": file_plan_artifact.content,
            "structured": file_plan_data,
        })
        logger.debug("[SprintSupervisor] FilePlanner: file_plan created")

        # Load architecture and user stories for context.
        architecture = store.read("project", "architecture") or {}
        user_stories = store.read("project", "user_stories") or {}

        # ===================================================================
        # Step 3: Backend + Frontend (sequential for now)
        # ===================================================================
        logger.debug("[SprintSupervisor] step 3: Backend + Frontend development")
        backend_agent = BackendDeveloperAgent(llm_manager=self.llm_manager)
        frontend_agent = FrontendDeveloperAgent(llm_manager=self.llm_manager)

        dev_ctx = SimpleNamespace(
            content=request,
            project_id=project_id,
            sprint=sprint_number,
        )
        backend_artifact = backend_agent.execute(dev_ctx)
        frontend_artifact = frontend_agent.execute(dev_ctx)
        logger.debug("[SprintSupervisor] Backend + Frontend: code generated")

        # ===================================================================
        # Step 4: TechLead review loop (max_dev_review_iterations)
        # ===================================================================
        logger.debug("[SprintSupervisor] step 4: TechLead review loop")
        tech_lead = TechLeadAgent(
            workspace_manager=self.workspace_manager,
            llm_manager=self.llm_manager,
        )

        dev_review_iteration = 0
        while dev_review_iteration < self._max_dev_review_iterations:
            dev_review_iteration += 1
            logger.debug(
                "[SprintSupervisor] TechLead review iteration %d/%d",
                dev_review_iteration,
                self._max_dev_review_iterations,
            )

            # Build review context from backend/frontend output + architecture + security rules.
            review_context = (
                f"=== TECH LEAD REVIEW ===\n"
                f"BACKEND OUTPUT:\n{backend_artifact.content}\n\n"
                f"FRONTEND OUTPUT:\n{frontend_artifact.content}\n\n"
                f"ARCHITECTURE:\n{json.dumps(architecture, indent=2)}\n\n"
                f"FILE PLAN:\n{json.dumps(file_plan_data, indent=2)}"
            )
            tech_review = tech_lead.review(
                project_id=project_id,
                sprint_number=sprint_number,
                context_text=review_context,
                iteration=dev_review_iteration,
            )

            if tech_review.get("approved", False):
                logger.info(
                    "[SprintSupervisor] TechLead approved sprint %d (iteration %d)",
                    sprint_number,
                    dev_review_iteration,
                )
                break
            else:
                if dev_review_iteration >= self._max_dev_review_iterations:
                    logger.warning(
                        "[SprintSupervisor] TechLead max retries exceeded for sprint %d",
                        sprint_number,
                    )
                    return SprintResult(
                        success=False,
                        blocked=True,
                        message=(
                            f"Sprint {sprint_number} blocked: TechLead approval failed after "
                            f"{self._max_dev_review_iterations} iterations. Violations: "
                            f"{tech_review.get('violations', [])}"
                        ),
                    )
                else:
                    logger.info(
                        "[SprintSupervisor] TechLead rejected sprint %d (iteration %d), re-running Backend+Frontend",
                        sprint_number,
                        dev_review_iteration,
                    )
                    # Re-run Backend + Frontend with violations as context.
                    violations_text = json.dumps(tech_review.get("violations", []), indent=2)
                    dev_ctx = SimpleNamespace(
                        content=(
                            f"{request}\n\n"
                            f"VIOLATIONS FROM PREVIOUS REVIEW (iteration {dev_review_iteration}):\n{violations_text}\n"
                            f"Fix the above violations and regenerate the code."
                        ),
                        project_id=project_id,
                        sprint=sprint_number,
                    )
                    backend_artifact = backend_agent.execute(dev_ctx)
                    frontend_artifact = frontend_agent.execute(dev_ctx)

        # ===================================================================
        # Step 5: QA loop (max_qa_iterations)
        # ===================================================================
        logger.debug("[SprintSupervisor] step 5: QA loop")
        qa_agent = QAAgent(
            workspace_manager=self.workspace_manager,
            llm_manager=self.llm_manager,
        )
        bug_analyst = BugAnalystAgent(
            workspace_manager=self.workspace_manager,
            llm_manager=self.llm_manager,
        )

        qa_iteration = 0
        while qa_iteration < self._max_qa_iterations:
            qa_iteration += 1
            logger.debug(
                "[SprintSupervisor] QA iteration %d/%d",
                qa_iteration,
                self._max_qa_iterations,
            )

            qa_findings = qa_agent.run_sprint_qa(
                project_id=project_id,
                sprint_number=sprint_number,
                file_plan=file_plan_data,
                architecture=architecture,
                user_stories=user_stories,
                iteration=qa_iteration,
            )

            if qa_findings.get("passed", False):
                logger.info(
                    "[SprintSupervisor] QA passed sprint %d (iteration %d)",
                    sprint_number,
                    qa_iteration,
                )
                break
            else:
                if qa_iteration >= self._max_qa_iterations:
                    logger.warning(
                        "[SprintSupervisor] QA max retries exceeded for sprint %d",
                        sprint_number,
                    )
                    return SprintResult(
                        success=False,
                        blocked=True,
                        message=(
                            f"Sprint {sprint_number} blocked: QA failed after "
                            f"{self._max_qa_iterations} iterations. Failures: "
                            f"{qa_findings.get('failures', [])}"
                        ),
                    )
                else:
                    logger.info(
                        "[SprintSupervisor] QA failed sprint %d (iteration %d), analyzing bugs",
                        sprint_number,
                        qa_iteration,
                    )
                    # Analyze root cause.
                    bug_analysis = bug_analyst.analyse(
                        project_id=project_id,
                        sprint_number=sprint_number,
                        qa_findings=json.dumps(qa_findings, indent=2),
                        user_stories=json.dumps(user_stories, indent=2),
                        architecture=json.dumps(architecture, indent=2),
                        file_plan=json.dumps(file_plan_data, indent=2),
                        iteration=qa_iteration,
                    )

                    bug_type = bug_analysis.get("type", "code_bug")
                    logger.info(
                        "[SprintSupervisor] bug classified as: %s (affected_agent: %s)",
                        bug_type,
                        bug_analysis.get("affected_agent", "Unknown"),
                    )

                    # Route fix based on bug type.
                    if bug_type == "code_bug":
                        logger.debug("[SprintSupervisor] routing code_bug back to Backend/Frontend")
                        fix_instruction = bug_analysis.get("fix_instruction", "See bug_analysis for details.")
                        dev_ctx = SimpleNamespace(
                            content=(
                                f"{request}\n\n"
                                f"BUG ANALYSIS (iteration {qa_iteration}):\n{fix_instruction}\n"
                                f"Fix the above bugs and regenerate the code."
                            ),
                            project_id=project_id,
                            sprint=sprint_number,
                        )
                        backend_artifact = backend_agent.execute(dev_ctx)
                        frontend_artifact = frontend_agent.execute(dev_ctx)
                        # Loop back to re-run TechLead review on the fixed code.
                        dev_review_iteration = 0
                    elif bug_type in ("spec_bug", "architecture_bug"):
                        logger.warning(
                            "[SprintSupervisor] %s detected; Phase 4 will add spec/arch update. "
                            "For now, routing as code_bug for developer fix.",
                            bug_type,
                        )
                        fix_instruction = bug_analysis.get("fix_instruction", "See bug_analysis for details.")
                        dev_ctx = SimpleNamespace(
                            content=(
                                f"{request}\n\n"
                                f"BUG ANALYSIS (iteration {qa_iteration}):\n{fix_instruction}\n"
                                f"Fix the above bugs and regenerate the code."
                            ),
                            project_id=project_id,
                            sprint=sprint_number,
                        )
                        backend_artifact = backend_agent.execute(dev_ctx)
                        frontend_artifact = frontend_agent.execute(dev_ctx)
                        # Loop back to re-run TechLead review.
                        dev_review_iteration = 0
                    else:
                        logger.error(
                            "[SprintSupervisor] unknown bug type: %s, blocking sprint",
                            bug_type,
                        )
                        return SprintResult(
                            success=False,
                            blocked=True,
                            message=(
                                f"Sprint {sprint_number} blocked: unknown bug type {bug_type}"
                            ),
                        )

        # ===================================================================
        # Step 6: SprintDeploy
        # ===================================================================
        logger.debug("[SprintSupervisor] step 6: SprintDeploy")
        deploy_agent = SprintDeployAgent(
            workspace_manager=self.workspace_manager,
            llm_manager=self.llm_manager,
        )
        deploy_status = deploy_agent.deploy_sprint(
            project_id=project_id,
            sprint_number=sprint_number,
            file_plan=file_plan_data,
        )
        logger.debug(
            "[SprintSupervisor] SprintDeploy: deployed=%s",
            deploy_status.get("deployed", False),
        )

        # ===================================================================
        # Step 7: SprintReview
        # ===================================================================
        logger.debug("[SprintSupervisor] step 7: SprintReview")
        review_agent = SprintReviewAgent(
            workspace_manager=self.workspace_manager,
            llm_manager=self.llm_manager,
        )
        sprint_review = review_agent.review_sprint(
            project_id=project_id,
            sprint_number=sprint_number,
            user_stories=user_stories,
            deploy_status=deploy_status,
            qa_findings=qa_findings,
        )
        logger.debug(
            "[SprintSupervisor] SprintReview: accepted=%s",
            sprint_review.get("accepted", False),
        )

        # ===================================================================
        # Step 8: Log sprint completion summary
        # ===================================================================
        logger.info(
            "[SprintSupervisor] sprint %d completed successfully: "
            "tasks=%d, techlead_iterations=%d, qa_iterations=%d, review_accepted=%s",
            sprint_number,
            len(tasks_data.get("tasks", [])),
            dev_review_iteration,
            qa_iteration,
            sprint_review.get("accepted", False),
        )

        # ===================================================================
        # Step 9: Return success
        # ===================================================================
        return SprintResult(
            success=True,
            blocked=False,
            message=f"Sprint {sprint_number} completed successfully",
        )
