from __future__ import annotations

import logging
import re
import time
from typing import Any

from ..artifact.manager import ArtifactManager
from ..shared.enums.stage import Stage
from ..shared.schemas.architecture_schema import ArchitectureArtifact
from ..shared.schemas.file_plan_schema import FilePlanArtifact, PlannedFile
from ..workspace.project_files import ProjectFileManager
from .architecture_summary import summarize_architecture
from .base_action import ActionOutput, BaseAction

logger = logging.getLogger(__name__)

_CODE_FENCE = re.compile(r"^```[a-zA-Z0-9_+-]*\s*\n(.*?)\n?```$", re.DOTALL)
_MIN_PLAUSIBLE_CHARS = 15


class WriteProjectFilesAction(BaseAction):
    """Shared per-file generation loop for BackendDeveloper/FrontendDeveloper.

    Replaces the old approach of asking the model to invent an entire app's
    worth of files in one JSON response: reads the File Plan produced by
    FileStructurePlanner, then makes one focused LLM call per file this
    stage is responsible for -- scoped to that file's purpose, the relevant
    architecture, and the sibling files already written this run (for
    import/naming consistency) -- and writes each result to a real file via
    ProjectFileManager instead of just embedding it in an artifact JSON blob.

    Subclasses set area/responsible_stage/role_label and supply their own
    prompt_builder (BackendPromptBuilder or FrontendPromptBuilder).
    """

    area: str = ""
    responsible_stage: str = ""
    role_label: str = ""

    def __init__(
        self,
        prompt_builder: Any,
        artifact_manager: ArtifactManager | None = None,
        project_file_manager: ProjectFileManager | None = None,
    ) -> None:
        """Wire the role-specific prompt builder, the ArtifactManager used to fetch the File Plan
        and Architecture, and the ProjectFileManager used to write real files."""
        self.prompt_builder = prompt_builder
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.project_file_manager = project_file_manager or ProjectFileManager(self.artifact_manager.workspace_manager)

    def run(self, context: object, llm: object) -> ActionOutput:
        """Generate and write every file this stage is responsible for, one focused LLM call each."""
        project_id = getattr(context, "project_id", "") or ""
        base_content = getattr(context, "content", "") or ""
        plan = self._load_file_plan(project_id)
        architecture = self._load_architecture(project_id)
        assigned = self._assigned_files(plan)

        written: list[str] = []
        skipped: list[str] = []
        siblings: list[str] = []
        total_tokens = 0
        total_latency = 0.0

        for planned_file in assigned:
            prompt = self._build_file_prompt(planned_file, architecture, base_content, siblings)
            started = time.time()
            response = llm.generate_text(prompt, system_prompt=self._system_prompt(), stage=self.name, agent=self.name)
            elapsed_ms = (time.time() - started) * 1000
            total_tokens += self._extract_tokens(response)
            total_latency += self._extract_latency_ms(response, elapsed_ms)

            file_content = self._extract_file_content(response.content)
            if not self._is_plausible(file_content):
                skipped.append(planned_file.path)
                logger.warning("%s: skipped implausible content for %s", self.name, planned_file.path)
                continue

            self.project_file_manager.write_file(project_id, self.area, planned_file.path, file_content)
            written.append(planned_file.path)
            siblings.append(f"{planned_file.path}: {planned_file.purpose}")

        manifest = self._build_manifest(project_id, assigned, written, skipped)
        structured = {
            "area": self.area,
            "planned_paths": [f.path for f in assigned],
            "written_paths": written,
            "skipped_paths": skipped,
        }
        return ActionOutput(content=manifest, structured=structured, tokens_used=total_tokens, latency_ms=total_latency)

    def _assigned_files(self, plan: FilePlanArtifact) -> list[PlannedFile]:
        """Return the plan's files this stage owns (no responsible_stage falls back to this stage)."""
        return [f for f in plan.files if f.path and (not f.responsible_stage or f.responsible_stage.lower() == self.responsible_stage)]

    def _load_file_plan(self, project_id: str) -> FilePlanArtifact:
        if not project_id:
            return FilePlanArtifact()
        artifact = self.artifact_manager.get_artifact(project_id, Stage.FileStructurePlanner)
        if artifact is None or not artifact.structured_content:
            return FilePlanArtifact()
        try:
            return FilePlanArtifact.model_validate(artifact.structured_content)
        except Exception as exc:
            logger.debug("%s: failed to parse File Plan: %s", self.name, exc)
            return FilePlanArtifact()

    def _load_architecture(self, project_id: str) -> ArchitectureArtifact | None:
        if not project_id:
            return None
        artifact = self.artifact_manager.get_artifact(project_id, Stage.Architect)
        if artifact is None or not artifact.structured_content:
            return None
        try:
            return ArchitectureArtifact.model_validate(artifact.structured_content)
        except Exception as exc:
            logger.debug("%s: failed to parse Architecture: %s", self.name, exc)
            return None

    def _build_file_prompt(
        self, planned_file: PlannedFile, architecture: ArchitectureArtifact | None, base_content: str, siblings: list[str],
    ) -> str:
        siblings_text = "\n".join(siblings) or "(none yet)"
        detail = (
            f"File to implement: {planned_file.path}\n"
            f"Module: {planned_file.module}\n"
            f"Purpose: {planned_file.purpose}\n\n"
            f"Relevant architecture:\n{summarize_architecture(architecture)}\n\n"
            f"Files already written this run (for import/naming consistency):\n{siblings_text}\n\n"
            f"Project context:\n{base_content}"
        )
        return self.prompt_builder.build(detail)

    def _build_manifest(self, project_id: str, assigned: list[PlannedFile], written: list[str], skipped: list[str]) -> str:
        lines = [
            f"# {self.role_label} Manifest",
            f"Project: {project_id or '(none)'}",
            f"Files planned: {len(assigned)}",
            f"Files written: {len(written)}",
        ]
        if written:
            lines.append("\n## Written")
            lines.extend(f"- {path}" for path in written)
        if skipped:
            lines.append("\n## Skipped (empty or implausible response)")
            lines.extend(f"- {path}" for path in skipped)
        if not assigned:
            lines.append(f"\nNo {self.area}-assigned files found in the File Plan.")
        return "\n".join(lines)

    def _system_prompt(self) -> str:
        return (
            f"You are a {self.role_label} implementing one specific file from an approved architecture "
            "and file plan. Respond with ONLY the complete file contents for the requested file -- no "
            "explanation, no JSON wrapper. You may wrap it in a single markdown code fence if you prefer, "
            "but the fence content must be the raw file only."
        )

    @staticmethod
    def _extract_file_content(text: str) -> str:
        text = (text or "").strip()
        match = _CODE_FENCE.match(text)
        if match:
            return match.group(1).strip()
        return text

    @staticmethod
    def _is_plausible(content: str) -> bool:
        return len(content.strip()) >= _MIN_PLAUSIBLE_CHARS

    def _extract_tokens(self, response: object) -> int:
        total = getattr(response, "total_tokens", None)
        if total is not None:
            return int(total)
        usage = getattr(response, "usage", None) or {}
        return int(usage.get("total", 0))

    def _extract_latency_ms(self, response: object, fallback_ms: float) -> float:
        latency = getattr(response, "latency", None)
        if latency:
            return latency * 1000
        return fallback_ms
