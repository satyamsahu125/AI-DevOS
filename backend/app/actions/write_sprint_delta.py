"""WriteSprintDeltaAction — decides create/update/patch per file for one sprint.

This action runs BEFORE FileStructurePlanner and produces explicit, reasoned
operation decisions that FileStructurePlanner consumes instead of inferring
them from a raw file list.  It eliminates the fragile pattern of "LLM reads
EXISTING FILES section and hopefully sets operation correctly".

Decision logic the LLM is asked to apply:
  create  — file does not exist yet; first time it is written
  update  — file exists AND this sprint's goal requires evolving its logic
             (e.g., Sprint 2 adds a payment_method field to an existing user model)
  patch   — file exists AND only a targeted, isolated change is needed
             (e.g., add one config key, fix one bug in one function)

For Sprint 1, all decisions are "create".  The action is non-blocking when it
fails — FileStructurePlanner falls back to its own FileRegistry-based inference.
"""
from __future__ import annotations

import logging
from typing import Any

from ..shared.schemas.sprint_delta_schema import FileOperationDecision, SprintDeltaArtifact
from .base_action import LLMAction

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a Senior Sprint Planner.

Your job: decide the correct file operation (create / update / patch) for every
file that will be touched in the upcoming sprint. You are given:

  1. The sprint goal and sprint number.
  2. The Architecture modules (with their declared file paths).
  3. EXISTING FILES — files already written in prior sprints.
  4. The prior sprint's file plan (what was written last sprint).

OPERATION DEFINITIONS:
  "create"  — file does not exist yet. Always use for Sprint 1.
  "update"  — file exists AND this sprint's goal requires new logic, new fields,
               new methods, or structural changes that extend the file significantly.
               Include a clear change_description explaining what to add/change.
  "patch"   — file exists AND only a small, targeted change is needed
               (add a config key, fix one function, add one import).
               Include a clear change_description of the exact change.

RULES:
  - A file in EXISTING FILES must be "update" or "patch", never "create".
  - A file NOT in EXISTING FILES must be "create".
  - If you are uncertain whether "update" or "patch" is correct, use "update".
  - List ALL files the sprint will touch — both new and modified.
  - Every "update" and "patch" decision MUST have a non-empty change_description.

Respond with ONLY a single JSON object. No explanation, no markdown.
"""


class WriteSprintDeltaAction(LLMAction):
    """Produces SprintDeltaArtifact with per-file operation decisions."""

    name = "WriteSprintDelta"
    description = "Decide create/update/patch operation per file for the upcoming sprint."
    schema_model = SprintDeltaArtifact
    system_prompt = _SYSTEM_PROMPT

    def __init__(
        self,
        artifact_manager: Any = None,
        file_registry: Any = None,
    ) -> None:
        # No PromptBuilder — prompt is constructed entirely here from injected dependencies.
        super().__init__(prompt_builder=None)
        self._artifact_manager = artifact_manager
        self._file_registry = file_registry

    def run(self, context: object, llm: object) -> Any:
        """Build a rich prompt from sprint context + FileRegistry, call the LLM, parse result."""
        from .base_action import ActionOutput
        project_id = getattr(context, "project_id", "") or ""
        sprint_number = int(getattr(context, "sprint_number", 1) or 1)
        sprint_goal = getattr(context, "content", "") or ""

        # Sprint 1 — all files are new; skip LLM call entirely
        if sprint_number <= 1:
            logger.info("SprintDelta: sprint 1 — all operations are 'create', skipping LLM")
            artifact = SprintDeltaArtifact(sprint_number=1, sprint_goal=sprint_goal)
            return ActionOutput(
                content="Sprint 1: all files are new (create).",
                structured=artifact.model_dump(mode="json"),
            )

        prompt = self._build_prompt(project_id, sprint_number, sprint_goal)
        response = llm.generate_text(
            prompt,
            system_prompt=self.system_prompt,
            stage=self.name,
            agent=self.name,
            project_id=project_id,
        )
        content = getattr(response, "content", str(response))
        structured = self._parse_structured(content)
        structured.setdefault("sprint_number", sprint_number)
        structured.setdefault("sprint_goal", sprint_goal)
        tokens = self._extract_tokens(response)
        return ActionOutput(content=content, structured=structured, tokens_used=tokens)

    def _build_prompt(self, project_id: str, sprint_number: int, sprint_goal: str) -> str:
        parts: list[str] = [
            f"SPRINT {sprint_number}",
            f"Goal: {sprint_goal}",
            "",
        ]

        # Existing files from FileRegistry
        existing_summary = ""
        if self._file_registry and project_id:
            try:
                existing_summary = self._file_registry.to_prompt_summary(project_id)
            except Exception as exc:
                logger.debug("SprintDelta: FileRegistry read failed: %s", exc)
        parts.append(existing_summary or "EXISTING FILES: (none — this is sprint 1 equivalent)")

        # Architecture modules with declared file paths
        arch_text = self._load_architecture_summary(project_id)
        if arch_text:
            parts.append(f"\nARCHITECTURE MODULES:\n{arch_text}")

        # Prior sprint's file plan — what was written last sprint
        prior_plan = self._load_prior_file_plan(project_id, sprint_number)
        if prior_plan:
            parts.append(f"\nPRIOR SPRINT FILE PLAN (sprint {sprint_number - 1}):\n{prior_plan}")

        parts.append(
            "\nBased on the sprint goal and existing files above, produce a SprintDeltaArtifact "
            "JSON with a 'decisions' list covering every file this sprint will touch."
        )
        return "\n".join(parts)

    def _load_architecture_summary(self, project_id: str) -> str:
        if not self._artifact_manager or not project_id:
            return ""
        try:
            from ..shared.enums.stage import Stage
            art = self._artifact_manager.get_artifact(project_id, Stage.Architect)
            if not art or not art.structured_content:
                return ""
            modules = art.structured_content.get("modules") or []
            lines: list[str] = []
            for mod in modules[:15]:
                if isinstance(mod, dict):
                    name = mod.get("name", "")
                    files = mod.get("files") or []
                    lines.append(f"  - {name}: {', '.join(files[:5])}")
                elif hasattr(mod, "name"):
                    files = list(getattr(mod, "files", []) or [])
                    lines.append(f"  - {mod.name}: {', '.join(files[:5])}")
            return "\n".join(lines)
        except Exception as exc:
            logger.debug("SprintDelta: architecture load failed: %s", exc)
            return ""

    def _load_prior_file_plan(self, project_id: str, sprint_number: int) -> str:
        if not self._artifact_manager or not project_id or sprint_number <= 1:
            return ""
        try:
            from ..shared.enums.stage import Stage
            art = self._artifact_manager.get_artifact(project_id, Stage.FileStructurePlanner)
            if not art or not art.structured_content:
                return ""
            files = art.structured_content.get("files") or []
            paths = [
                (f.get("path", "") if isinstance(f, dict) else getattr(f, "path", ""))
                for f in files
            ]
            return "Files from prior sprint: " + ", ".join(p for p in paths[:20] if p)
        except Exception as exc:
            logger.debug("SprintDelta: prior file plan load failed: %s", exc)
            return ""

    def _parse_structured(self, content: str) -> dict[str, Any]:
        data = self.extract_json(content)
        try:
            parsed = SprintDeltaArtifact.model_validate(data)
            return parsed.model_dump(mode="json")
        except Exception:
            return SprintDeltaArtifact().model_dump(mode="json")

    @staticmethod
    def _extract_tokens(response: object) -> int:
        total = getattr(response, "total_tokens", None)
        if total is not None:
            return int(total)
        usage = getattr(response, "usage", None) or {}
        return int(usage.get("total", 0))
