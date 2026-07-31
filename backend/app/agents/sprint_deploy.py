"""SprintDeployAgent — lightweight per-sprint staging deployment.

Simulates deploying a sprint's increment to a staging environment.
No real infrastructure needed — output is a deployment summary describing
what services would start, what issues were encountered, etc.

Output structure::

    {
      "deployed": bool,
      "staging_url": "http://staging.local/v{N}",
      "services_started": [...],
      "issues": [...],
      "summary": str,
      "sprint": N
    }

Output is written to::

    artifacts/sprint_{N}/deploy_status.json

via :class:`~app.workspace.artifact_store.ArtifactStore`.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..actions.base_action import ActionOutput, BaseAction
from ..llm.manager import LLMManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a DevOps engineer deploying a software sprint increment to staging.

You receive:
- The file plan (what files were built this sprint)

Your job is to simulate a staging deployment and produce a summary:

{
  "deployed": true | false,
  "staging_url": "http://staging.local/v{sprint_number}",
  "services_started": [
    "<service name>",
    ...
  ],
  "issues": [
    {
      "service": "<service name>",
      "issue": "<what went wrong>"
    }
  ],
  "summary": "<one sentence deployment status>",
  "sprint": <sprint number integer>
}

Rules:
- deployed=true ONLY when all services start cleanly and no issues exist.
- deployed=false when ANY service fails to start or ANY issue is found.
- services_started lists all services that started without error.
- issues lists all problems found during staging deployment (empty if deployed=true).
- Be realistic about potential deployment issues based on the code built.

Output ONLY valid JSON — no markdown, no explanation outside it.
"""


# ---------------------------------------------------------------------------
# Primary action
# ---------------------------------------------------------------------------

class _DeploySrintAction(BaseAction):
    """Simulate staging deployment for a sprint's built code."""

    name = "DeploySprint"
    description = "Simulate staging deployment and return deployment status."

    def run(self, context: object, llm: object) -> ActionOutput:  # type: ignore[override]
        content = getattr(context, "content", str(context)) if context is not None else ""
        sprint = getattr(context, "sprint_number", 1)

        prompt = (
            f"=== SPRINT DEPLOYMENT REQUEST (Sprint {sprint}) ===\n\n"
            f"{content}\n\n"
            "Simulate a staging deployment and output the status as a JSON object."
        )

        response = llm.generate_text(
            prompt,
            system_prompt=_SYSTEM_PROMPT,
            stage="SprintDeploy",
            agent="SprintDeployAgent",
        )
        structured = self.extract_json(response.content)

        # Ensure required fields exist.
        if "deployed" not in structured:
            structured["deployed"] = False
        if "staging_url" not in structured:
            structured["staging_url"] = f"http://staging.local/v{sprint}"
        if "services_started" not in structured:
            structured["services_started"] = []
        if "issues" not in structured:
            structured["issues"] = []
        if "summary" not in structured:
            structured["summary"] = "Deployment simulation incomplete"
        structured["sprint"] = sprint

        return ActionOutput(content=response.content, structured=structured)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class SprintDeployAgent(BaseAgent):
    """Lightweight staging deployment agent for per-sprint deployments.

    Simulates deploying a sprint's increment to a staging environment.
    Produces a structured deployment status for WorkflowManager to evaluate.

    Parameters
    ----------
    workspace_manager:
        Injected so the agent can write to ArtifactStore.  ``None`` in
        unit-test paths where the write is skipped.
    llm_manager:
        The LLM provider.  Defaults to ``LLMManager()`` if not injected.
    primary_action:
        Overrides the default :class:`_DeploySrintAction` (useful in tests).
    """

    artifact_name = "deploy_status"

    def __init__(
        self,
        workspace_manager=None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
    ) -> None:
        self._workspace_manager = workspace_manager
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return _DeploySrintAction()

    def deploy_sprint(
        self,
        project_id: str,
        sprint_number: int,
        file_plan: dict,
    ) -> dict:
        """Simulate staging deployment for a sprint and return deployment status.

        Builds a deployment context from file_plan, calls the LLM, writes
        result to sprint-scoped ArtifactStore, and returns the dict.

        Parameters
        ----------
        project_id:
            Project identifier.
        sprint_number:
            Sprint number (1-indexed).
        file_plan:
            Dictionary describing files built in this sprint.

        Returns
        -------
        dict
            Deployment status: ``{"deployed": bool, "staging_url": str, ...}``.
        """
        from types import SimpleNamespace

        context_text = f"FILE PLAN:\n{json.dumps(file_plan, indent=2)}"
        ctx = SimpleNamespace(
            project_id=project_id,
            sprint_number=sprint_number,
            content=context_text,
        )
        artifact = self.execute(ctx)

        # Persist to sprint-scoped ArtifactStore when workspace_manager is wired.
        if self._workspace_manager is not None:
            try:
                store = self._workspace_manager.get_artifact_store(project_id)
                store.write(
                    scope=f"sprint_{sprint_number}",
                    name="deploy_status",
                    data={
                        "content": artifact.content,
                        "structured": artifact.structured_content or {},
                        "stage": "SprintDeploy",
                        "written_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as exc:
                logger.warning(
                    "[SprintDeployAgent] non-fatal ArtifactStore write failure: %s", exc
                )

        return artifact.structured_content or {
            "deployed": False,
            "staging_url": f"http://staging.local/v{sprint_number}",
            "services_started": [],
            "issues": [],
            "summary": "Deployment failed",
            "sprint": sprint_number,
        }
