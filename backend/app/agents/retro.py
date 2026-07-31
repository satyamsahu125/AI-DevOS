from __future__ import annotations

import json
import logging
from typing import Any

from ..actions.base_action import BaseAction
from ..actions.write_retrospective import WriteRetrospectiveAction
from ..llm.manager import LLMManager
from ..prompt.retro_builder import RetroPromptBuilder
from ..workspace.artifact_store import ArtifactStore
from ..workspace.manager import WorkspaceManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class RetroAgent(BaseAgent):
    """Retro agent: summarizes the sprint via WriteRetrospectiveAction.

    Prompt from gstack's /retro persona. Output schema: SprintRetrospective.
    Also provides run_sprint_retro() and run_project_retro() methods for phase 4.
    """

    artifact_name = "retro-output"

    def __init__(
        self,
        prompt_builder: RetroPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        workspace_manager: WorkspaceManager | None = None,
    ) -> None:
        """Wire this agent's prompt builder and (via BaseAgent) its LLMManager and primary_action."""
        self._prompt_builder = prompt_builder
        self._workspace_manager = workspace_manager
        super().__init__(llm_manager, primary_action)

    def _build_default_action(self) -> BaseAction:
        """Build this agent's default action: WriteRetrospectiveAction."""
        return WriteRetrospectiveAction(self._prompt_builder)

    def run_sprint_retro(
        self,
        project_id: str,
        sprint_number: int,
        sprint_review: dict,
        qa_findings: dict,
        tech_review: dict,
    ) -> dict:
        """Summarise what was learned in this sprint. Called by WorkflowManager at end of each sprint.

        Parameters
        ----------
        project_id : str
            Project identifier.
        sprint_number : int
            Sprint number (1-indexed).
        sprint_review : dict
            Output from SprintReviewAgent.
        qa_findings : dict
            Output from QAAgent.run_sprint_qa().
        tech_review : dict
            Output from TechLeadAgent.review().

        Returns
        -------
        dict
            Sprint retrospective with what_worked, what_didnt, improvements, summary.
        """
        prompt = (
            f"=== SPRINT {sprint_number} RETROSPECTIVE ===\n\n"
            f"SPRINT REVIEW:\n{json.dumps(sprint_review, indent=2)}\n\n"
            f"QA FINDINGS:\n{json.dumps(qa_findings, indent=2)}\n\n"
            f"TECH REVIEW:\n{json.dumps(tech_review, indent=2)}\n\n"
            f"Synthesise this sprint's lessons learned:\n"
            f"1. What worked well (features completed, processes, collaboration)?\n"
            f"2. What didn't work (blockers, misunderstandings, rework)?\n"
            f"3. Concrete improvements for next sprint?\n\n"
            f"Return JSON:\n{{\n"
            f'  "sprint": {sprint_number},\n'
            f'  "what_worked": [...],\n'
            f'  "what_didnt": [...],\n'
            f'  "improvements": [...],\n'
            f'  "summary": "..."\n'
            f"}}"
        )

        try:
            content = self.llm_manager.generate_text(prompt)
            # Extract JSON from response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                retro_data = json.loads(json_str)
            else:
                retro_data = {}
        except Exception as exc:
            logger.warning("[RetroAgent] run_sprint_retro JSON parse failed: %s", exc)
            retro_data = {}

        # Apply safe defaults
        retro_data.setdefault("sprint", sprint_number)
        retro_data.setdefault("what_worked", [])
        retro_data.setdefault("what_didnt", [])
        retro_data.setdefault("improvements", [])
        retro_data.setdefault("summary", "No summary")

        # Write to ArtifactStore
        if self._workspace_manager:
            store = self._workspace_manager.get_artifact_store(project_id)
            store.write(f"sprint_{sprint_number}", "sprint_retro", retro_data)

            # Also append summary to retro log
            retro_log_path = store._scope_dir("project") / "retro_log.txt"
            log_entry = f"[Sprint {sprint_number}] {retro_data.get('summary', 'No summary')}\n"
            if retro_log_path.exists():
                retro_log_path.write_text(retro_log_path.read_text() + log_entry, encoding="utf-8")
            else:
                retro_log_path.write_text(log_entry, encoding="utf-8")

        return retro_data

    def run_project_retro(
        self,
        project_id: str,
        sprint_retros: list[dict],
    ) -> dict:
        """Synthesise all sprint retros into a project-level retrospective.

        Called in Release phase to produce final project-level lessons.

        Parameters
        ----------
        project_id : str
            Project identifier.
        sprint_retros : list[dict]
            List of sprint retrospective dicts from run_sprint_retro().

        Returns
        -------
        dict
            Project retrospective with recurring patterns and recommendations.
        """
        prompt = (
            f"=== PROJECT RETROSPECTIVE ===\n\n"
            f"You are conducting a project-level retrospective across {len(sprint_retros)} sprints.\n\n"
            f"SPRINT RETROSPECTIVES:\n{json.dumps(sprint_retros, indent=2)}\n\n"
            f"Synthesise patterns and lessons across all sprints:\n"
            f"1. Recurring wins — what worked consistently?\n"
            f"2. Recurring issues — what kept happening?\n"
            f"3. Architectural lessons — what did you learn about the system design?\n"
            f"4. Process improvements — how should the team work differently next time?\n\n"
            f"Return JSON:\n{{\n"
            f'  "total_sprints": {len(sprint_retros)},\n'
            f'  "recurring_wins": [...],\n'
            f'  "recurring_issues": [...],\n'
            f'  "architectural_lessons": [...],\n'
            f'  "process_improvements": [...],\n'
            f'  "summary": "..."\n'
            f"}}"
        )

        try:
            content = self.llm_manager.generate_text(prompt)
            # Extract JSON from response
            json_start = content.find("{")
            json_end = content.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = content[json_start:json_end]
                retro_data = json.loads(json_str)
            else:
                retro_data = {}
        except Exception as exc:
            logger.warning("[RetroAgent] run_project_retro JSON parse failed: %s", exc)
            retro_data = {}

        # Apply safe defaults
        retro_data.setdefault("total_sprints", len(sprint_retros))
        retro_data.setdefault("recurring_wins", [])
        retro_data.setdefault("recurring_issues", [])
        retro_data.setdefault("architectural_lessons", [])
        retro_data.setdefault("process_improvements", [])
        retro_data.setdefault("summary", "No summary")

        # Write to ArtifactStore
        if self._workspace_manager:
            store = self._workspace_manager.get_artifact_store(project_id)
            store.write("release", "project_retro", retro_data)

        return retro_data
