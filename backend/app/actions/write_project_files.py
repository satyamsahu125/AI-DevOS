from __future__ import annotations

import logging
import re
import time
from typing import Any

from ..artifact.manager import ArtifactManager
from ..shared.enums.stage import Stage
from ..shared.schemas.architecture_schema import ArchitectureArtifact
from ..shared.schemas.file_plan_schema import FilePlanArtifact, PlannedFile
from ..workspace.dependency_detector import (
    build_package_json,
    build_requirements_txt,
    detect_node_dependencies,
    detect_python_dependencies,
)
from ..workspace.file_registry import FileRegistry
from ..workspace.project_files import ProjectFileManager
from ..workspace.project_readme import summarize_area
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
        file_registry: FileRegistry | None = None,
    ) -> None:
        """Wire the role-specific prompt builder, the ArtifactManager used to fetch the File Plan
        and Architecture, the ProjectFileManager used to write real files, and the optional
        FileRegistry that tracks existing files for Agile update semantics."""
        self.prompt_builder = prompt_builder
        self.artifact_manager = artifact_manager or ArtifactManager()
        self.project_file_manager = project_file_manager or ProjectFileManager(self.artifact_manager.workspace_manager)
        # Phase 8: FileRegistry tracks which files already exist so Sprint 2+ can update them
        self.file_registry = file_registry or FileRegistry(
            workspace_manager=getattr(self.artifact_manager, "workspace_manager", None)
        )

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
        file_contents: list[str] = []
        total_tokens = 0
        total_latency = 0.0

        for planned_file in assigned:
            prompt = self._build_file_prompt(planned_file, architecture, base_content, siblings, project_id=project_id)
            started = time.time()
            response = llm.generate_text(prompt, system_prompt=self._system_prompt(), stage=self.name, agent=self.name, project_id=project_id)
            elapsed_ms = (time.time() - started) * 1000
            total_tokens += self._extract_tokens(response)
            total_latency += self._extract_latency_ms(response, elapsed_ms)

            file_content = self._extract_file_content(response.content)
            if not self._is_plausible(file_content):
                skipped.append(planned_file.path)
                logger.warning("%s: skipped implausible content for %s", self.name, planned_file.path)
                continue

            self.project_file_manager.write_file(project_id, self.area, self._relative_write_path(planned_file.path), file_content)
            written.append(planned_file.path)
            file_contents.append(file_content)
            siblings.append(f"{planned_file.path}: {planned_file.purpose}")
            # Phase 8: record in FileRegistry so future sprints know this file exists
            sprint_number = getattr(context, "sprint_number", 0) or 0
            self.file_registry.record(project_id, planned_file.path, sprint_number)

        manifest_path = self._write_dependency_manifest(project_id, written, file_contents)
        if manifest_path:
            written.append(manifest_path)

        manifest = self._build_manifest(project_id, assigned, written, skipped)
        structured = {
            "area": self.area,
            "planned_paths": [f.path for f in assigned],
            "written_paths": written,
            "skipped_paths": skipped,
        }
        return ActionOutput(content=manifest, structured=structured, tokens_used=total_tokens, latency_ms=total_latency)

    def _write_dependency_manifest(self, project_id: str, written: list[str], file_contents: list[str]) -> str | None:
        """Detect this area's stack from what was actually written, scan those files' own import
        statements for external packages, and write a starter package.json/requirements.txt --
        so "how to run" isn't just advice, the file that makes `npm install`/`pip install -r
        requirements.txt` actually do something is really there. Skipped if a manifest was
        already planned/written for this area, or the stack isn't one this can generate for.
        No-op (never a failure) if nothing was written at all.
        """
        if not written:
            return None
        summary = summarize_area(self.area, written)
        if summary.has_manifest:
            return None
        if summary.detected_stack == "node":
            dependencies = detect_node_dependencies(file_contents)
            if not dependencies:
                return None
            content = build_package_json(project_id, dependencies, written)
            self.project_file_manager.write_file(project_id, self.area, "package.json", content)
            return "package.json"
        if summary.detected_stack == "python":
            dependencies = detect_python_dependencies(file_contents)
            if not dependencies:
                return None
            content = build_requirements_txt(dependencies)
            self.project_file_manager.write_file(project_id, self.area, "requirements.txt", content)
            return "requirements.txt"
        return None

    def _relative_write_path(self, path: str) -> str:
        """Strip a leading "{area}/" prefix from path if present.

        ProjectFileManager.write_file() already scopes the write to self.area
        (e.g. "backend"), but the File Plan's LLM-authored paths commonly
        already include that same prefix (e.g. "backend/models/Task.js") --
        without this, the two would combine into a doubled, wrong path like
        project/backend/backend/models/Task.js. planned_file.path itself is
        left untouched for the written/skipped manifest, which stays
        readable either way.

        When area="" (mobile projects writing to project root), no prefix is
        stripped — the path is used verbatim.
        """
        if not self.area:
            # Mobile / root-level writes: path is already relative to project root
            return path
        prefix = f"{self.area}/"
        if path.lower().startswith(prefix.lower()):
            return path[len(prefix):]
        return path

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
        self,
        planned_file: PlannedFile,
        architecture: ArchitectureArtifact | None,
        base_content: str,
        siblings: list[str],
        project_id: str = "",
    ) -> str:
        siblings_text = "\n".join(siblings) or "(none yet)"
        operation = getattr(planned_file, "operation", "create") or "create"
        change_description = getattr(planned_file, "change_description", "") or ""

        # Phase 8: for update/patch, read existing file content and inject it.
        existing_content: str | None = None
        if operation in ("update", "patch") and project_id:
            relative_path = self._relative_write_path(planned_file.path)
            existing_content = self.project_file_manager.read_file(project_id, self.area, relative_path)

        if operation == "create" or existing_content is None:
            # Standard create prompt — no existing content available
            detail = (
                f"Operation: CREATE (new file)\n"
                f"File to implement: {planned_file.path}\n"
                f"Module: {planned_file.module}\n"
                f"Purpose: {planned_file.purpose}\n\n"
                f"Relevant architecture:\n{summarize_architecture(architecture)}\n\n"
                f"Files already written this run (for import/naming consistency):\n{siblings_text}\n\n"
                f"Project context:\n{base_content}"
            )
        elif operation == "patch":
            # Targeted change — include existing content and specific change instruction
            change_instruction = change_description or planned_file.purpose
            detail = (
                f"Operation: PATCH (targeted change to existing file)\n"
                f"File: {planned_file.path}\n"
                f"What to change: {change_instruction}\n\n"
                f"EXISTING FILE CONTENT (apply your changes to this):\n"
                f"```\n{existing_content}\n```\n\n"
                f"Return the COMPLETE updated file with the patch applied. "
                f"Do NOT rewrite unrelated parts of the file.\n\n"
                f"Relevant architecture:\n{summarize_architecture(architecture)}\n\n"
                f"Files already written this run:\n{siblings_text}"
            )
        else:
            # update — rewrite with new features/sprint goals added
            change_instruction = change_description or planned_file.purpose
            detail = (
                f"Operation: UPDATE (evolve existing file for new sprint)\n"
                f"File: {planned_file.path}\n"
                f"Module: {planned_file.module}\n"
                f"What to add/change: {change_instruction}\n\n"
                f"EXISTING FILE CONTENT (extend and update this — preserve working functionality):\n"
                f"```\n{existing_content}\n```\n\n"
                f"Return the COMPLETE updated file content including both existing and new code.\n\n"
                f"Relevant architecture:\n{summarize_architecture(architecture)}\n\n"
                f"Files already written this run:\n{siblings_text}\n\n"
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
