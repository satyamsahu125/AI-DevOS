from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import threading

from ..actions.base_action import BaseAction
from ..actions.write_frontend_code import WriteFrontendCodeAction
from ..artifact.manager import ArtifactManager
from ..execution.file_validator import FileValidator
from ..execution.project_writer import ProjectWriter
from ..llm.manager import LLMManager
from ..prompt.frontend_builder import FrontendPromptBuilder
from ..shared.dto.sprint_execution import FileGenerationResult, SprintExecutionResult
from ..shared.language_profile import LanguageProfile
from ..shared.language_registry import LanguageProfileRegistry
from ..shared.schemas.file_plan_schema import FilePlan, FileSpec
from ..workspace.manager import WorkspaceManager
from ..workspace.project_files import ProjectFileManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class FrontendDeveloperAgent(BaseAgent):
    """Generates frontend code file by file.

    Each LLM call produces clean code files. Validates before writing. Retries
    with error feedback. Writes real files to temp-workspace/{id}/project/

    Language profile resolution
    ---------------------------
    The agent detects the correct frontend framework from the sprint context
    using :class:`~app.shared.language_registry.LanguageProfileRegistry`.
    It reads the ``"frontend"`` key of ``tech_stack`` exclusively — backend
    language choices do not influence the frontend profile.

    Resolution happens *once* per sprint (at the top of :meth:`execute_sprint`)
    and is cached in :attr:`_resolved_profile` for observability.

    Injection order:
    1. ``language_profile`` constructor arg (explicit; useful in tests).
    2. ``file_plan.tech_stack["frontend"]`` parsed via the registry.
    3. ``context`` parsed for ``tech_stack["frontend"]``.
    4. Hard fallback to ``react_vite`` (always the frontend default).

    Parallel file generation
    ------------------------
    When ``SPRINT_PARALLEL_FILES`` is set to a value > 1 in the environment,
    independent frontend files are dispatched concurrently in dependency-ordered
    waves using a :class:`~concurrent.futures.ThreadPoolExecutor`.  The sequential
    path (``SPRINT_PARALLEL_FILES`` ≤ 1 or unset) is identical to the original
    implementation — no regression.
    """

    MAX_ATTEMPTS_PER_FILE = 3
    artifact_name = "frontend"

    # Default profile key used when no frontend technology is detectable.
    _DEFAULT_PROFILE_KEY: str = "react_vite"

    def __init__(
        self,
        prompt_builder: FrontendPromptBuilder | None = None,
        llm_manager: LLMManager | None = None,
        primary_action: BaseAction | None = None,
        artifact_manager: ArtifactManager | None = None,
        project_file_manager: ProjectFileManager | None = None,
        project_writer: ProjectWriter | None = None,
        validator: FileValidator | None = None,
        workspace_manager: WorkspaceManager | None = None,
        file_indexer: object | None = None,
        language_profile: LanguageProfile | None = None,
        memory_manager: object | None = None,
    ) -> None:
        self._prompt_builder = prompt_builder
        self._artifact_manager = artifact_manager
        self._project_file_manager = project_file_manager
        self.project_writer = project_writer or ProjectWriter(workspace_manager)
        self.validator = validator or FileValidator()
        self._file_indexer = file_indexer  # FIX 5: use summaries for large dependency files
        self._memory_manager = memory_manager
        # Language profile: explicit injection wins; otherwise resolved per-sprint from context.
        self._language_profile: LanguageProfile | None = language_profile
        # Populated by _resolve_language_profile; exposed for observability / testing.
        self._resolved_profile: LanguageProfile | None = None
        super().__init__(llm_manager=llm_manager, primary_action=primary_action)

    def _build_default_action(self) -> BaseAction:
        return WriteFrontendCodeAction(self._prompt_builder, self._artifact_manager, self._project_file_manager)

    # ------------------------------------------------------------------
    # Language profile resolution
    # ------------------------------------------------------------------

    def _resolve_language_profile(self, context: object) -> LanguageProfile:
        """Return the :class:`LanguageProfile` for the current sprint's frontend.

        The frontend agent exclusively uses the ``"frontend"`` key of
        ``tech_stack`` for detection (e.g. ``"React/Vite"`` → ``react_vite``,
        ``"Vue/Vite"`` → ``vue_vite``).  Backend language choices (Go, Rust,
        Java …) are deliberately ignored.

        Resolution order:

        1. Explicit injection (``self._language_profile`` set at construction time).
        2. ``context`` parsed for ``tech_stack["frontend"]``.
        3. Hard fallback to ``react_vite``.

        The result is stored in ``self._resolved_profile`` for observability after
        the sprint completes.

        Parameters
        ----------
        context:
            The sprint context (dict, JSON string, StageArtifact, etc.).
        """
        if self._language_profile is not None:
            self._resolved_profile = self._language_profile
            logger.debug(
                "%s using explicitly injected language profile: language=%s framework=%s",
                type(self).__name__,
                self._resolved_profile.language,
                self._resolved_profile.framework,
            )
            return self._resolved_profile

        # Extract only the frontend value from tech_stack so the registry's
        # backend detection branch does NOT fire.
        frontend_tech_stack = self._extract_frontend_tech_stack(context)
        registry = LanguageProfileRegistry()
        self._resolved_profile = registry.detect_from_tech_stack(frontend_tech_stack)

        # If the registry fell back to python_fastapi (unrecognised frontend),
        # swap in the frontend default (react_vite) instead.
        if self._resolved_profile.language == "python":
            self._resolved_profile = registry.get(self._DEFAULT_PROFILE_KEY)

        logger.info(
            "%s resolved language profile: language=%s framework=%s (frontend_tech_stack=%s)",
            type(self).__name__,
            self._resolved_profile.language,
            self._resolved_profile.framework,
            frontend_tech_stack,
        )
        return self._resolved_profile

    def _extract_frontend_tech_stack(self, context: object) -> dict:
        """Extract a tech_stack dict keyed for frontend-only detection.

        Returns ``{"frontend": "<value>"}`` when the context contains a
        ``tech_stack["frontend"]`` entry, so that
        :meth:`LanguageProfileRegistry.detect_from_tech_stack` uses its
        frontend-only detection branch (which fires when ``backend`` is absent).

        Returns an empty dict on any failure (triggers ``react_vite`` fallback).

        This method NEVER raises.
        """
        try:
            raw_tech_stack = self._extract_raw_tech_stack(context)
            frontend_val = raw_tech_stack.get("frontend")
            if frontend_val:
                # Pass ONLY the frontend key so the registry skips backend rules
                return {"frontend": str(frontend_val)}
        except Exception:  # noqa: BLE001
            pass
        return {}

    def _extract_raw_tech_stack(self, context: object) -> dict:
        """Extract the full ``tech_stack`` dict from any context shape.

        Mirrors the logic in :class:`~app.agents.backend.BackendDeveloperAgent`
        to handle all known context forms:

        * StageArtifact with ``.content`` (JSON string).
        * Plain dict with ``"tech_stack"`` key.
        * Dict with ``"backend"`` / ``"frontend"`` / ``"database"`` keys (IS tech_stack).
        * Nested under ``"architect"`` / ``"architecture"``.
        * JSON string.
        * Object with ``.tech_stack`` attribute.

        Returns empty dict on any failure — never raises.
        """
        try:
            # StageArtifact / object with .content
            content_attr = getattr(context, "content", None)
            if content_attr is not None:
                return self._extract_raw_tech_stack(content_attr)

            if isinstance(context, dict):
                # Already a tech_stack dict
                if any(k in context for k in ("backend", "frontend", "database")):
                    return context
                # {"tech_stack": {...}}
                ts = context.get("tech_stack")
                if isinstance(ts, dict):
                    return ts
                if isinstance(ts, str):
                    return {"frontend": ts}
                # Nested under "architect" / "architecture"
                for nesting_key in ("architect", "architecture"):
                    nested = context.get(nesting_key)
                    if isinstance(nested, dict):
                        ts = nested.get("tech_stack")
                        if isinstance(ts, dict):
                            return ts
                    elif isinstance(nested, str):
                        try:
                            parsed_nested = json.loads(nested)
                            if isinstance(parsed_nested, dict):
                                ts = parsed_nested.get("tech_stack")
                                if isinstance(ts, dict):
                                    return ts
                        except (ValueError, TypeError):
                            pass
                return {}

            if isinstance(context, str):
                try:
                    parsed = json.loads(context)
                    if isinstance(parsed, dict):
                        return self._extract_raw_tech_stack(parsed)
                except (ValueError, TypeError):
                    pass
                return {}

            ts_attr = getattr(context, "tech_stack", None)
            if isinstance(ts_attr, dict):
                return ts_attr

        except Exception:  # noqa: BLE001
            pass

        return {}

    # ------------------------------------------------------------------
    # Sprint execution
    # ------------------------------------------------------------------

    def execute_sprint(
        self,
        project_id: str,
        file_plan: FilePlan,
        context: object | None = None,
        design_artifact: dict | str | None = None,
    ) -> SprintExecutionResult:
        """Execute all frontend files in this sprint.

        design_artifact is the approved design spec; when provided it is
        injected into every file prompt so no frontend code is written
        without it. None keeps the prompt unchanged.

        Language profile is resolved *once* at sprint start — preferring
        ``file_plan.tech_stack`` (most reliable) then falling back to ``context``.

        When ``SPRINT_PARALLEL_FILES > 1``, files with satisfied dependencies are
        dispatched concurrently in waves.  The sequential path
        (``SPRINT_PARALLEL_FILES`` ≤ 1 or unset) is byte-for-byte identical to the
        original implementation — no regression.
        """
        # Resolve profile ONCE for the entire sprint.
        # Priority: file_plan.tech_stack (architect-approved) → context
        _resolve_src: object = getattr(file_plan, "tech_stack", None) or context
        profile = self._resolve_language_profile(_resolve_src)

        gen_order = getattr(file_plan, "generation_order", []) or []
        files_map = getattr(file_plan, "files", {}) or {}

        # Read folder structure from blueprint to determine frontend paths dynamically.
        # Falls back to the old "frontend/" prefix if no blueprint is available.
        _blueprint_raw = None
        if getattr(self, "_memory_manager", None) is not None:
            try:
                _blueprint_raw = self._memory_manager.load(project_id, "blueprint:latest")
            except Exception:
                pass

        if not _blueprint_raw:
            try:
                from ..memory.blueprint_store import BlueprintStore
                bp_store = BlueprintStore(workspace_manager=getattr(self.project_writer, "workspace", None))
                _bp_dict = bp_store.get(project_id)
                if _bp_dict:
                    _blueprint_raw = _bp_dict
            except Exception:
                pass

        if _blueprint_raw:
            _bp = json.loads(_blueprint_raw) if isinstance(_blueprint_raw, str) else _blueprint_raw
            _frontend_paths = tuple(
                node["path"].rstrip("/")
                for node in _bp.get("folder_structure", [])
                if isinstance(node, dict) and node.get("owner") in ("frontend", "shared")
            )
            if _frontend_paths:
                frontend_files = [
                    fp for fp in gen_order
                    if any(fp.startswith(p) for p in _frontend_paths)
                ]
                if not frontend_files and files_map:
                    frontend_files = [
                        fp for fp in files_map
                        if any(fp.startswith(p) for p in _frontend_paths)
                    ]
            else:
                frontend_files = list(gen_order) or list(files_map.keys())
            logger.info(
                "[FrontendAgent] blueprint folder filter: paths=%s files=%d project=%s",
                _frontend_paths, len(frontend_files), project_id,
            )
        else:
            logger.warning(
                "[FrontendAgent] no blueprint found — using legacy 'frontend/' prefix filter: project=%s",
                project_id,
            )
            frontend_files = [fp for fp in gen_order if fp.startswith("frontend/")]
            if not frontend_files and files_map:
                frontend_files = [fp for fp in files_map if fp.startswith("frontend/")]

        max_workers = int(os.getenv("SPRINT_PARALLEL_FILES", "1"))

        if max_workers <= 1 or len(frontend_files) <= 1:
            # ── Sequential path — original behaviour, no regression ───────────
            written_files: list[FileGenerationResult] = []
            failed_files: list[FileGenerationResult] = []

            for file_path in frontend_files:
                # Default language comes from the resolved profile, not hardcoded "typescript"
                file_spec = files_map.get(file_path) or FileSpec(
                    file_path=file_path, language=profile.language
                )
                result = self._generate_one_file(
                    project_id=project_id,
                    file_path=file_path,
                    file_spec=file_spec,
                    file_plan=file_plan,
                    context=context,
                    design_artifact=design_artifact,
                    profile=profile,
                )
                if result.success:
                    written_files.append(result)
                    self._index_file_if_available(project_id, file_path)
                else:
                    failed_files.append(result)
                    logger.error(
                        "Failed to generate: %s after %d attempts",
                        file_path, self.MAX_ATTEMPTS_PER_FILE,
                    )
        else:
            # ── Parallel path — DAG wave execution ────────────────────────────
            logger.info(
                "FrontendDeveloperAgent: parallel sprint execution: "
                "files=%d max_workers=%d",
                len(frontend_files), max_workers,
            )
            written_files, failed_files = self._execute_sprint_parallel(
                project_id=project_id,
                file_list=frontend_files,
                files_map=files_map,
                file_plan=file_plan,
                context=context,
                design_artifact=design_artifact,
                profile=profile,
                max_workers=max_workers,
            )

        return SprintExecutionResult(
            sprint_number=file_plan.sprint_number,
            written_files=written_files,
            failed_files=failed_files,
            success=len(failed_files) == 0,
        )

    def _execute_sprint_parallel(
        self,
        project_id: str,
        file_list: list[str],
        files_map: dict,
        file_plan: FilePlan,
        context: object | None,
        design_artifact: dict | str | None,
        profile: LanguageProfile,
        max_workers: int,
    ) -> tuple[list[FileGenerationResult], list[FileGenerationResult]]:
        """Execute frontend file generation in dependency-ordered waves.

        Mirrors :meth:`BackendDeveloperAgent._execute_sprint_parallel` with
        one additional parameter: ``design_artifact`` is forwarded to every
        :meth:`_generate_one_file` call so each worker thread receives the
        approved design spec.

        See the backend agent's docstring for the full algorithm description.

        Parameters
        ----------
        file_list:
            Ordered list of ``frontend/…`` paths (respects ``generation_order``).
        files_map:
            ``{file_path: FileSpec}`` from the file plan.
        design_artifact:
            The approved design spec (forwarded to every ``_generate_one_file``).
        max_workers:
            Maximum concurrent threads per wave (from ``SPRINT_PARALLEL_FILES``).

        Returns
        -------
        (written_files, failed_files)
        """
        written_files: list[FileGenerationResult] = []
        failed_files: list[FileGenerationResult] = []

        completed: set[str] = set()
        failed: set[str] = set()      # noqa: F841  (kept for symmetry / future use)
        scheduled: set[str] = set()

        all_file_set: set[str] = set(file_list)
        _results_lock = threading.Lock()

        def _run_one(fp: str) -> FileGenerationResult:
            file_spec = files_map.get(fp) or FileSpec(
                file_path=fp, language=profile.language
            )
            return self._generate_one_file(
                project_id=project_id,
                file_path=fp,
                file_spec=file_spec,
                file_plan=file_plan,
                context=context,
                design_artifact=design_artifact,
                profile=profile,
            )

        wave_number = 0
        while True:
            wave: list[str] = []
            for fp in file_list:
                if fp in scheduled:
                    continue
                file_spec = files_map.get(fp)
                deps: list[str] = (
                    (getattr(file_spec, "depends_on", None) or []) if file_spec else []
                )
                if all(d in completed or d not in all_file_set for d in deps):
                    wave.append(fp)

            if not wave:
                break

            wave_number += 1
            scheduled.update(wave)
            logger.info(
                "FrontendDeveloperAgent: wave %d — %d file(s): %s",
                wave_number, len(wave), wave,
            )

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_path: dict[concurrent.futures.Future, str] = {
                    executor.submit(_run_one, fp): fp for fp in wave
                }

                for future in concurrent.futures.as_completed(future_to_path):
                    fp = future_to_path[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # noqa: BLE001
                        logger.error(
                            "FrontendDeveloperAgent: unexpected exception generating %s: %s",
                            fp, exc, exc_info=True,
                        )
                        result = FileGenerationResult(
                            file_path=fp,
                            success=False,
                            attempts=self.MAX_ATTEMPTS_PER_FILE,
                            last_error=str(exc),
                        )

                    if result.success:
                        completed.add(fp)
                        self._index_file_if_available(project_id, fp)
                        with _results_lock:
                            written_files.append(result)
                        logger.debug(
                            "FrontendDeveloperAgent: wave %d done: %s", wave_number, fp,
                        )
                    else:
                        failed.add(fp)
                        logger.error(
                            "FrontendDeveloperAgent: wave %d failed: %s after %d attempts",
                            wave_number, fp, self.MAX_ATTEMPTS_PER_FILE,
                        )
                        with _results_lock:
                            failed_files.append(result)

        orphaned = [fp for fp in file_list if fp not in scheduled]
        for fp in orphaned:
            logger.warning(
                "FrontendDeveloperAgent: skipping %s — "
                "one or more dependencies failed to generate",
                fp,
            )
            failed_files.append(
                FileGenerationResult(
                    file_path=fp,
                    success=False,
                    attempts=0,
                    last_error="Skipped: dependency failed or was never generated",
                )
            )

        logger.info(
            "FrontendDeveloperAgent: parallel sprint done — "
            "waves=%d written=%d failed=%d",
            wave_number, len(written_files), len(failed_files),
        )
        return written_files, failed_files

    def _index_file_if_available(self, project_id: str, file_path: str) -> None:
        """Call ``ProjectSymbolIndex.index_file()`` immediately after a file is written.

        Called from both sequential and parallel paths so the symbol index stays
        fresh regardless of execution mode.

        Non-fatal: any exception is logged, never propagated.  No-op when
        ``_file_indexer`` is ``None`` or lacks an ``index_file`` method.

        Thread safety: ``ProjectSymbolIndex`` is guarded by an ``RLock`` internally.

        Parameters
        ----------
        project_id:
            Active project identifier.
        file_path:
            Repo-relative path of the file just written.
        """
        if self._file_indexer is None:
            return
        index_fn = getattr(self._file_indexer, "index_file", None)
        if index_fn is None:
            return
        try:
            index_fn(project_id, file_path)
            logger.debug("indexed: %s", file_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "index_file failed for %s (non-fatal): %s", file_path, exc,
            )

    def _generate_one_file(
        self,
        project_id: str,
        file_path: str,
        file_spec: FileSpec,
        file_plan: FilePlan,
        context: object | None,
        profile: LanguageProfile,
        design_artifact: dict | str | None = None,
    ) -> FileGenerationResult:
        """Generate, validate, and write ONE file.

        Parameters
        ----------
        profile:
            The language profile resolved at sprint start by
            :meth:`_resolve_language_profile`.
        """
        last_error = ""

        for attempt in range(1, self.MAX_ATTEMPTS_PER_FILE + 1):
            prompt = self._build_file_prompt(
                file_spec=file_spec,
                file_plan=file_plan,
                project_id=project_id,
                previous_error=last_error,
                attempt=attempt,
                design_artifact=design_artifact,
            )

            response = self.llm_manager.generate_text(
                prompt=prompt,
                system_prompt=self._file_system_prompt(profile),
                stage="frontend",
                project_id=project_id,
            )
            raw_content = getattr(response, "content", str(response))
            content = self._extract_code(raw_content)

            validation = self.validator.validate(
                file_path=file_path,
                content=content,
                language=file_spec.language or profile.language,
            )

            if validation.passed:
                written = self.project_writer.write_file(
                    project_id=project_id,
                    file_path=file_path,
                    content=content,
                    attempt=attempt,
                )
                logger.info("✓ Generated: %s (attempt %d)", file_path, attempt)
                return FileGenerationResult(
                    file_path=file_path,
                    success=True,
                    attempts=attempt,
                    written_file=written,
                )
            else:
                last_error = "\n".join(validation.errors)
                logger.warning("✗ Validation failed attempt %d: %s — %s", attempt, file_path, last_error)

        return FileGenerationResult(
            file_path=file_path,
            success=False,
            attempts=self.MAX_ATTEMPTS_PER_FILE,
            last_error=last_error,
        )

    def _build_file_prompt(
        self,
        file_spec: FileSpec,
        file_plan: FilePlan,
        project_id: str,
        previous_error: str,
        attempt: int,
        design_artifact: dict | str | None = None,
        sprint_brief: str = "",
    ) -> str:
        """Build prompt for ONE file generation, including the approved design spec.

        FIX 5: Uses FileIndexer summaries for large dependency files.
        """
        _FULL_CONTENT_THRESHOLD = 1500
        design_context = self._build_design_context(design_artifact)
        dependency_context = ""
        deps = getattr(file_spec, "depends_on", []) or []
        for dep_path in deps[:3]:
            dep_content = self.project_writer.read_file(project_id, dep_path)
            if dep_content and len(dep_content) <= _FULL_CONTENT_THRESHOLD:
                dependency_context += f"\n\n// {dep_path}:\n{dep_content}"
            elif self._file_indexer is not None:
                summary = self._file_indexer.get_file_summary(project_id, dep_path)
                if summary:
                    dependency_context += f"\n\n// {dep_path} (summary):\n{summary}"
            elif dep_content:
                dependency_context += f"\n\n// {dep_path} (first 1500 chars):\n{dep_content[:1500]}"

        error_context = ""
        if previous_error:
            error_context = f"\nPREVIOUS ATTEMPT FAILED WITH THESE ERRORS:\n{previous_error}\nFix these errors in your response.\n"

        req_imports = "\n".join(f"  - {imp}" for imp in (getattr(file_spec, "required_imports", []) or []))

        sprint_context = f"{sprint_brief}\n\n" if sprint_brief else ""
        return f"""{sprint_context}Generate the file: {file_spec.file_path}

Purpose: {file_spec.purpose}
Language: {file_spec.language}
Tech stack: {file_plan.tech_stack}

Required imports (must include all of these):
{req_imports}

Required components / classes to implement:
{file_spec.required_classes}

Required functions / hooks to implement:
{file_spec.required_functions}

Exports from this file:
{file_spec.exports}

These dependency files already exist (for context):
{dependency_context}
{design_context}
{error_context}
Write ONLY the complete {file_spec.file_path} file.
No explanation. No markdown. No code fences. Just the code.
"""

    def _build_design_context(self, design_artifact: dict | str | None) -> str:
        """Render the approved design spec into a prompt block.

        Returns "" when there is no design, leaving the prompt unchanged.
        A non-dict design (raw Designer text that never parsed as JSON) is
        passed through verbatim rather than dropped.
        """
        if not design_artifact:
            return ""
        if not isinstance(design_artifact, dict):
            return (
                "\nAPPROVED DESIGN SPECIFICATION (implement exactly this):\n"
                f"{str(design_artifact)[:2000]}\n"
            )

        components = design_artifact.get("components") or []
        pages = design_artifact.get("pages") or []
        palette = design_artifact.get("color_palette") or {}

        component_lines = "\n".join(
            f"  - {component.get('name', '')}: {component.get('shadcn_component', '')}"
            f" classes={component.get('tailwind_classes', '')}"
            for component in components[:10]
            if isinstance(component, dict)
        )
        page_names = [page.get("name", "") for page in pages if isinstance(page, dict)]

        return (
            "\nAPPROVED DESIGN SPECIFICATION (implement exactly this):\n"
            f"  Color palette: {palette}\n"
            f"  Typography: {design_artifact.get('typography', {})}\n"
            f"  Border radius: {design_artifact.get('border_radius', '')}\n"
            f"  Pages: {page_names}\n"
            f"  Components to implement:\n{component_lines}\n"
        )

    def _file_system_prompt(self, profile: LanguageProfile) -> str:
        """Return the LLM system prompt for code generation using the resolved language profile.

        The prompt comes from :attr:`LanguageProfile.system_prompt`, authored for
        the exact frontend framework detected from the architect's tech_stack.
        This replaces the previously hardcoded ``"React/TypeScript developer"`` string.

        Parameters
        ----------
        profile:
            The language profile resolved at sprint start by
            :meth:`_resolve_language_profile`.
        """
        return profile.system_prompt

    def _extract_code(self, response: str) -> str:
        """Strip any accidental markdown fences."""
        content = response.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)
        return content
