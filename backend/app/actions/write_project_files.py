from __future__ import annotations

import logging
import re
import time
from typing import Any

from ..artifact.manager import ArtifactManager
from ..execution.syntax_validator import SyntaxValidator
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

# re.DOTALL + re.MULTILINE so the pattern works with or without LLM preamble text.
# re.search (not re.match) is used below so the fence is found anywhere in the string.
_CODE_FENCE = re.compile(r"```[a-zA-Z0-9_+-]*\s*\n(.*?)\n?```", re.DOTALL)
_MIN_PLAUSIBLE_CHARS = 15

# Stub-body detection — a function/method whose body (after an optional docstring)
# is only "pass". Regex: def foo(...): [optional docstring] \n    pass
_STUB_FUNC_RE = re.compile(
    r"(?:async\s+)?def\s+\w+[^:]*:\s*\n"
    r"(?:\s+(?:\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?''')\s*\n)?"  # optional docstring
    r"\s+pass\s*(?:\n|$)",
    re.MULTILINE,
)
# Any function/method definition — used to compute stub ratio
_FUNC_DEF_RE = re.compile(r"(?:async\s+)?def\s+\w+", re.MULTILINE)
# Minimum stub count that qualifies a file as a stub file.
# A single "pass" in a helper can be intentional; ≥2 means the AI scaffolded but didn't fill in.
_MIN_STUB_FUNCS_FOR_FLAG = 2
# How many times to re-prompt the LLM when a file fails syntax validation.
# Each retry injects the error message so the model knows exactly what to fix.
_MAX_SYNTAX_RETRIES = 2

_syntax_validator = SyntaxValidator()


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

    def _get_area(self, project_id: str) -> str:  # noqa: ARG002
        """Return the write-area string for this project.

        Default implementation returns the class-level ``area`` attribute.
        Subclasses (e.g. WriteFrontendCodeAction) override this to compute the
        area dynamically from the project's Architecture artifact so that the
        result is always fresh and never stored on ``self`` — which would cause
        a data race when multiple projects run concurrently through a singleton
        action instance.
        """
        return self.area

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

        # Resolve area once per run() call — never written to self.area so concurrent
        # projects sharing a singleton action instance cannot corrupt each other.
        resolved_area = self._get_area(project_id)

        written: list[str] = []
        skipped: list[str] = []
        stub_paths: list[str] = []      # files with ≥2 pass-only function bodies
        syntax_fix_paths: list[str] = [] # files that needed a syntax re-prompt
        siblings: list[str] = []
        file_contents: list[str] = []
        total_tokens = 0
        total_latency = 0.0
        # Prefer an explicit sprint_number on context; fall back to what
        # SprintExecutor recorded in project.json via set_current_sprint().
        sprint_number = getattr(context, "sprint_number", None)
        if sprint_number is None:
            try:
                ws = getattr(self.artifact_manager, "workspace_manager", None)
                if ws is not None:
                    ws_data = ws.load_project_json(project_id) or {}
                    sprint_number = int(ws_data.get("current_sprint_number", 0))
                else:
                    sprint_number = 0
            except Exception:
                sprint_number = 0

        for planned_file in assigned:
            prompt = self._build_file_prompt(planned_file, architecture, base_content, siblings, project_id=project_id)

            # ── Generation + syntax validation + retry loop ───────────────────
            file_content: str | None = None
            for attempt in range(_MAX_SYNTAX_RETRIES + 1):
                started = time.time()
                response = llm.generate_text(
                    prompt,
                    system_prompt=self._system_prompt(),
                    stage=self.name, agent=self.name, project_id=project_id,
                )
                elapsed_ms = (time.time() - started) * 1000
                total_tokens += self._extract_tokens(response)
                total_latency += self._extract_latency_ms(response, elapsed_ms)

                candidate = self._extract_file_content(response.content)
                if not self._is_plausible(candidate):
                    logger.warning("%s: implausible content attempt %d for %s", self.name, attempt + 1, planned_file.path)
                    break  # won't improve with retry — skip this file

                syntax_issue = _syntax_validator.validate(planned_file.path, candidate)
                if syntax_issue is None:
                    file_content = candidate
                    if attempt > 0:
                        syntax_fix_paths.append(planned_file.path)
                        logger.info(
                            "%s: syntax fixed on attempt %d for %s",
                            self.name, attempt + 1, planned_file.path,
                        )
                    break  # clean — proceed to write

                # Syntax error found — inject error into prompt and retry
                logger.warning(
                    "%s: syntax error in %s (attempt %d/%d): %s",
                    self.name, planned_file.path, attempt + 1, _MAX_SYNTAX_RETRIES + 1,
                    syntax_issue.message,
                )
                if attempt < _MAX_SYNTAX_RETRIES:
                    # Prepend the error hint so the next attempt knows what to fix
                    prompt = syntax_issue.as_prompt_hint() + "\n\n" + prompt
                else:
                    # Exhausted retries — write the last candidate anyway so the
                    # file exists (reviewer will flag it, BackendDev can patch it)
                    file_content = candidate
                    logger.warning(
                        "%s: writing %s despite syntax error after %d retries — "
                        "reviewer will flag for re-generation",
                        self.name, planned_file.path, _MAX_SYNTAX_RETRIES,
                    )

            if file_content is None:
                skipped.append(planned_file.path)
                logger.warning("%s: skipped %s (no plausible content after retries)", self.name, planned_file.path)
                continue
            # ─────────────────────────────────────────────────────────────────

            # P8-3: map PlannedFile.operation → write_mode for the file-manager safety guard.
            #   create → "create"    (guard: skip if file already exists)
            #   update → "overwrite" (agent produced full replacement content)
            #   patch  → "patch"     (agent produced merged content; write as-is)
            _op = getattr(planned_file, "operation", "create") or "create"
            _write_mode = "create" if _op == "create" else ("patch" if _op == "patch" else "overwrite")
            self.project_file_manager.write_file(
                project_id,
                resolved_area,
                self._relative_write_path(planned_file.path),
                file_content,
                write_mode=_write_mode,
            )
            written.append(planned_file.path)
            file_contents.append(file_content)
            siblings.append(f"{planned_file.path}: {planned_file.purpose}")
            # Phase 8: record in FileRegistry so future sprints know this file exists
            self.file_registry.record(project_id, planned_file.path, sprint_number)

            # Stub detection: flag files whose LLM output is scaffolded but unimplemented
            stub_count = self._count_stub_bodies(file_content)
            if stub_count >= _MIN_STUB_FUNCS_FOR_FLAG:
                stub_paths.append(planned_file.path)
                logger.warning(
                    "%s: stub body detected in %s (%d pass-only functions)",
                    self.name, planned_file.path, stub_count,
                )

        manifest_path = self._write_dependency_manifest(project_id, written, file_contents)
        if manifest_path:
            written.append(manifest_path)

        # Post-generation hook — subclasses override to do extra work with the
        # written files (e.g. BackendDev extracts API contract for FrontendDev).
        self._post_generate(project_id, list(zip(written, file_contents)))

        manifest = self._build_manifest(project_id, assigned, written, skipped)
        structured = {
            "area": resolved_area,
            "planned_paths": [f.path for f in assigned],
            "written_paths": written,
            "skipped_paths": skipped,
            "stub_paths": stub_paths,              # files with pass-only stubs
            "syntax_fix_paths": syntax_fix_paths,  # files that required syntax re-prompt
        }
        return ActionOutput(content=manifest, structured=structured, tokens_used=total_tokens, latency_ms=total_latency)

    def _post_generate(self, project_id: str, written_files: list[tuple[str, str]]) -> None:
        """Called after all files are written.  Subclasses override for post-processing."""

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

    def _area_for_file_read(self, architecture: ArchitectureArtifact | None) -> str:  # noqa: ARG002
        """Return the area string to pass to ProjectFileManager.read_file() when injecting
        existing file content into the generation prompt for update/patch operations.

        Default: self.area (the class-level attribute).

        Subclasses that resolve their area dynamically (e.g. WriteFrontendCodeAction, which
        returns "" for mobile projects and "frontend" for web) override this method so that
        read_file() looks in the same directory that write_file() writes to — instead of
        always using the class-level attribute, which may differ at runtime.
        """
        return self.area

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

    @staticmethod
    def _module_contract_section(planned_file: PlannedFile, architecture: ArchitectureArtifact | None) -> str:
        """Return an 'Exports contract' section if the owning module declares exports.

        Finds the Architecture ModuleSpec whose files list includes this file's
        path, then emits a concise list of what this file MUST export so that
        sibling files that import from it get the right symbols.
        """
        if architecture is None:
            return ""
        file_path_lower = planned_file.path.lower()
        for module in (architecture.modules or []):
            module_files = [f.lower() for f in (module.files or [])]
            if file_path_lower in module_files or any(file_path_lower.endswith(mf) for mf in module_files):
                exports = [e for e in (module.exports or []) if e]
                if exports:
                    lines = [
                        f"\n## Module Contract — {module.name}",
                        f"This file belongs to the '{module.name}' module. "
                        f"It MUST export the following symbols so other modules can import them:",
                    ]
                    for exp in exports:
                        lines.append(f"  - {exp}")
                    lines.append(
                        "Do NOT rename, omit, or relocate these symbols. "
                        "Other files generated in this sprint will import them by these exact names."
                    )
                    return "\n".join(lines)
        return ""

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

        # Module export contract — injected so the LLM knows which symbols this
        # file must export for sibling files to import correctly.
        contract_section = self._module_contract_section(planned_file, architecture)

        # Phase 8: for update/patch, read existing file content and inject it.
        # The area used for reading is resolved via _area_for_file_read() so subclasses
        # (e.g. WriteFrontendCodeAction) can override it when the runtime area differs
        # from the class-level self.area attribute (e.g. mobile vs web projects).
        existing_content: str | None = None
        if operation in ("update", "patch") and project_id:
            relative_path = self._relative_write_path(planned_file.path)
            read_area = self._area_for_file_read(architecture)
            existing_content = self.project_file_manager.read_file(project_id, read_area, relative_path)

        if operation == "create" or existing_content is None:
            # Standard create prompt — no existing content available
            detail = (
                f"Operation: CREATE (new file)\n"
                f"File to implement: {planned_file.path}\n"
                f"Module: {planned_file.module}\n"
                f"Purpose: {planned_file.purpose}\n"
                f"{contract_section}\n\n"
                f"IMPLEMENTATION REQUIREMENTS:\n"
                f"- Implement ALL operations/methods/endpoints described in the purpose above\n"
                f"- Use domain-specific names matching the actual project entities in the architecture\n"
                f"- Include error handling, logging, and input validation throughout\n"
                f"- Do NOT write generic/placeholder code — every line must serve the actual project\n\n"
                f"Relevant architecture:\n{summarize_architecture(architecture)}\n\n"
                f"Files already written this run (import from these for consistency):\n{siblings_text}\n\n"
                f"Project context:\n{base_content}"
            )
        elif operation == "patch":
            # Targeted change — include existing content and specific change instruction
            change_instruction = change_description or planned_file.purpose
            detail = (
                f"Operation: PATCH (targeted change to existing file)\n"
                f"File: {planned_file.path}\n"
                f"What to change: {change_instruction}\n"
                f"{contract_section}\n\n"
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
            "and file plan.\n\n"
            "COMPLETENESS RULES — NEVER VIOLATE:\n"
            "1. Implement EVERY method, function, class, and route described in the file's purpose "
            "and the architecture. No stubs, no TODOs, no placeholder comments like '# implement here'.\n"
            "2. Every function body must contain real logic — calculations, DB queries, API calls, "
            "validation, error handling — not just 'pass' or 'return None'.\n"
            "3. A service file should be 300-600 lines covering all operations for its domain entity. "
            "A router/controller file should implement all CRUD endpoints plus domain-specific actions. "
            "A model file should define all fields, relationships, indexes, and helper methods.\n"
            "4. Use domain-specific variable names and logic that match the project's actual entities "
            "(e.g. for a food delivery app: Restaurant, MenuItem, Order, Delivery — not generic 'Item' or 'Entity').\n"
            "5. Include proper error handling (try/except or equivalent) on every I/O operation.\n"
            "6. For UPDATE operations: read the existing file content provided, then produce the FULL "
            "updated file — keep all working code, add the new sprint's features on top.\n\n"
            "Respond with ONLY the complete file contents — no explanation, no JSON wrapper. "
            "You may use a single markdown code fence, but the fence content must be the raw file only."
        )

    @staticmethod
    def _extract_file_content(text: str) -> str:
        # Use re.search so a code fence is found even when the LLM prefixes
        # prose before the first triple-backtick (very common in practice).
        text = (text or "").strip()
        match = _CODE_FENCE.search(text)
        if match:
            return match.group(1).strip()
        return text

    @staticmethod
    def _is_plausible(content: str) -> bool:
        return len(content.strip()) >= _MIN_PLAUSIBLE_CHARS

    @staticmethod
    def _count_stub_bodies(content: str) -> int:
        """Count function/method definitions whose body is only 'pass'.

        A count ≥ _MIN_STUB_FUNCS_FOR_FLAG indicates the LLM scaffolded the
        file but did not implement it.  Single-pass bodies (abstract helpers,
        empty __init__) are intentional and filtered out by the threshold.
        """
        return len(_STUB_FUNC_RE.findall(content))

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
