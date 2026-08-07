from __future__ import annotations

import logging
from pydantic import BaseModel, Field

from ..artifact.manager import ArtifactManager
from ..llm.manager import LLMManager
from ..workflow.manager import WorkflowManager
from ..workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)


class ChatResponse(BaseModel):
    reply: str
    action_taken: str | None = None
    stage_triggered: str | None = None
    artifacts_read: list[str] = Field(default_factory=list)


class ChatRouter:
    """Routes chat messages to the right agent or action.
    Not a stage agent — a conversational interface.
    """

    STAGE_KEYWORDS = {
        "strategy": "strategic_review",
        "strategic": "strategic_review",
        "requirements": "product_owner",
        "product owner": "product_owner",
        "po": "product_owner",
        "prd": "product_owner",
        "architect": "architect",
        "architecture": "architect",
        "design": "designer",
        "designer": "designer",
        "security": "security",
        "sprint": "sprint_planner",
        "scrum master": "scrum_master",
        "scrum": "scrum_master",
        "files": "file_planner",
        "file structure": "file_planner",
        "file": "file_planner",
        "backend": "backend",
        "frontend": "frontend",
        "qa": "qa",
        "test": "qa",
        "docs": "document",
        "document": "document",
        "devops": "devops",
        "deploy": "devops",
        "retrospective": "retro",
        "retro": "retro",
    }

    ACTION_KEYWORDS = {
        "re-run": "trigger_stage",
        "rerun": "trigger_stage",
        "run again": "trigger_stage",
        "redo": "trigger_stage",
        "retry": "trigger_stage",
        "show": "read_artifact",
        "explain": "read_artifact",
        "what did": "read_artifact",
        "summarize": "read_artifact",
        "status": "get_status",
        "progress": "get_status",
        "how many": "get_status",
    }

    def __init__(
        self,
        llm_manager: LLMManager,
        artifact_manager: ArtifactManager,
        workflow_manager: WorkflowManager,
        workspace_manager: WorkspaceManager,
    ) -> None:
        self.llm = llm_manager
        self.artifacts = artifact_manager
        self.workflow = workflow_manager
        self.workspace = workspace_manager

    def handle(
        self,
        project_id: str,
        message: str
    ) -> ChatResponse:
        """Route message to correct handler."""
        msg_lower = message.lower()

        # Detect intent
        action = self._detect_action(msg_lower)
        stage = self._detect_stage(msg_lower)

        if action == "trigger_stage" and stage:
            return self._trigger_stage(project_id, stage, message)
        elif action in ("read_artifact", None) and stage:
            return self._read_and_explain_artifact(project_id, stage, message)
        elif action == "get_status":
            return self._get_status(project_id)
        else:
            # General question — use LLM with project context
            return self._general_answer(project_id, message)

    def _detect_action(self, msg: str) -> str | None:
        for keyword, action in self.ACTION_KEYWORDS.items():
            if keyword in msg:
                return action
        return None

    def _detect_stage(self, msg: str) -> str | None:
        for keyword, stage in self.STAGE_KEYWORDS.items():
            if keyword in msg:
                return stage
        return None

    def _read_and_explain_artifact(
        self,
        project_id: str,
        stage: str,
        question: str
    ) -> ChatResponse:
        artifact = self.artifacts.get_artifact(project_id, stage)
        if not artifact or not artifact.content:
            return ChatResponse(
                reply=f"The {stage} stage hasn't run yet for this project.",
                artifacts_read=[]
            )

        prompt = f"""
You are helping a user understand their project.

The user asked: {question}

Here is the {stage} stage output:
{artifact.content[:3000]}

Answer the user's question clearly and concisely.
Focus on what they asked. Be specific, not generic.
"""
        llm_response = self.llm.generate_text(
            prompt=prompt,
            system_prompt=(
                "You are a helpful assistant answering questions about an AI-generated software project. "
                "Be specific, reference actual content from the artifact, never make things up."
            )
        )
        return ChatResponse(
            reply=llm_response.content,
            artifacts_read=[stage]
        )

    def _trigger_stage(
        self,
        project_id: str,
        stage: str,
        message: str
    ) -> ChatResponse:
        """Trigger a stage re-run."""
        project_json = self.workspace.load_project_json(project_id) or {}
        original_request = (
            project_json.get("original_request")
            or project_json.get("description")
            or f"Re-run stage {stage}"
        )

        result = self.workflow.run_stage(
            project_id=project_id,
            stage_name=stage,
            content=original_request
        )

        return ChatResponse(
            reply=(
                f"I've re-run the {stage} stage. "
                f"{'It completed successfully.' if result.success else 'It encountered issues — check the logs.'}"
            ),
            action_taken=f"triggered_{stage}",
            stage_triggered=stage
        )

    def _get_status(self, project_id: str) -> ChatResponse:
        project_json = self.workspace.load_project_json(project_id) or {}
        completed = project_json.get("stages_completed", [])
        current = project_json.get("current_stage", "none")
        state = project_json.get("state", "unknown")
        total = 14  # total stages

        return ChatResponse(
            reply=(
                f"Project status: {state}\n"
                f"Completed: {len(completed)}/{total} stages\n"
                f"Current stage: {current}\n"
                f"Stages done: {', '.join(completed) or 'none'}"
            )
        )

    def _general_answer(
        self,
        project_id: str,
        message: str
    ) -> ChatResponse:
        """Handle general questions with project context."""
        project_json = self.workspace.load_project_json(project_id) or {}
        completed = project_json.get("stages_completed", [])

        context_parts = []
        for stage in completed[-3:]:
            artifact = self.artifacts.get_artifact(project_id, stage)
            if artifact and artifact.content:
                context_parts.append(f"[{stage}]: {artifact.content[:500]}")

        context = "\n\n".join(context_parts)

        prompt = f"""
You are helping a user with their software project.

Project context from recent stages:
{context}

User question: {message}

Answer helpfully based on the project context.
If the answer isn't in the context, say so clearly.
"""
        llm_response = self.llm.generate_text(
            prompt=prompt,
            system_prompt=(
                "You are a knowledgeable software engineering assistant helping a user understand and manage "
                "their AI-generated software project."
            )
        )
        return ChatResponse(reply=llm_response.content)
