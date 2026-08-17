from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import threading

from ..actions.base_action import BaseAction
from ..actions.write_backend_code import WriteBackendCodeAction
from ..artifact.manager import ArtifactManager
from ..execution.file_validator import FileValidator
from ..execution.project_writer import ProjectWriter
from ..llm.manager import LLMManager
from ..prompt.backend_builder import BackendPromptBuilder
from ..shared.dto.sprint_execution import FileGenerationResult, SprintExecutionResult
from ..shared.language_profile import LanguageProfile
from ..shared.language_registry import LanguageProfileRegistry
from ..shared.schemas.file_plan_schema import FilePlan, FileSpec
from ..workspace.manager import WorkspaceManager
from ..workspace.project_files import ProjectFileManager
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class BackendDeveloperAgent(BaseAgent):
    """Generates backend code file by file.

    Each LLM call produces clean code files. Validates before writing. Retries
    with error feedback. Writes real files to temp-workspace/{id}/project/

    Language profile resolution
    ---------------------------
    The agent detects the correct language/framework from the sprint context
    using :class:`~app.shared.language_registry.LanguageProfileRegistry`.
    Resolution happens *once* per sprint (at the top of :meth:`execute_sprint`)
    and is cached in :attr:`_resolved_profile` for observability.

    Injection order:
    1. ``language_profile`` constructor arg (explicit; useful in tests).
    2. ``file_plan.tech_stack`` parsed via the registry (primary runtime path).
    3. ``context`` dict/JSON/object parsed via the registry.
    4. Hard fallback to ``python_fastapi`` (registry guarantees this).

    Parallel file generation
    ------------------------
    When ``SPRINT_PARALLEL_FILES`` is set to a value > 1 in the environment,
    independent files (no overlapping ``depends_on``) are dispatched concurrently
    in dependency-ordered waves using a :class:`~concurrent.futures.ThreadPoolExecutor`.

    Wave 1: all files whose ``depends_on`` list is empty or references only
    external (pre-existing) files.
    Wave N: all files whose every dependency completed successfully in a prior wave.

    A file whose dependency failed is never scheduled and is reported as
    orphaned (``Skipped: dependency failed``).

    When ``SPRINT_PARALLEL_FILES`` ≤ 1 or the variable is unset, behaviour is
    identical to the original sequential loop — no regression.
    """

    MAX_ATTEMPTS_PER_FILE = 3
    artifact_name = "backend"

    def __init__(
        self,
        prompt_builder: BackendPromptBuilder | None = None,
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
        return WriteBackendCodeAction(self._prompt_builder, self._artifact_manager, self._project_file_manager)

    # ------------------------------------------------------------------
    # Language profile resolution
    # ------------------------------------------------------------------

    def _resolve_language_profile(self, context: object) -> LanguageProfile:
        """Return the :class:`LanguageProfile` for the current sprint.

        Resolution order:

        1. Explicit injection (``self._language_profile`` set at construction time).
        2. ``context`` parsed for a ``tech_stack`` mapping that is passed to
           :meth:`LanguageProfileRegistry.detect_from_tech_stack`.
        3. Hard fallback to ``python_fastapi`` (registry guarantees this — never raises).

        The result is stored in ``self._resolved_profile`` for observability after
        the sprint completes.

        Parameters
        ----------
        context:
            The sprint context.  May be a plain ``dict``, a JSON ``str``, a
            :class:`~app.shared.models.stage_artifact.StageArtifact` with a
            ``.content`` attribute, or any other object.  Parsing failures are
            silently swallowed — they result in the ``python_fastapi`` fallback.
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

        tech_stack = self._extract_tech_stack(context)
        registry = LanguageProfileRegistry()
        self._resolved_profile = registry.detect_from_tech_stack(tech_stack)
        logger.info(
            "%s resolved language profile: language=%s framework=%s (tech_stack=%s)",
            type(self).__name__,
            self._resolved_profile.language,
            self._resolved_profile.framework,
            tech_stack,
        )
        return self._resolved_profile

    def _extract_tech_stack(self, context: object) -> dict:
        """Extract a ``tech_stack`` dict from any context shape.

        Handles the following forms, in order:

        * A ``dict`` whose top-level keys include ``"backend"`` / ``"frontend"``
          / ``"database"`` — treated as a tech_stack dict directly.
        * A ``dict`` with a ``"tech_stack"`` key (value may be dict or str).
        * A ``dict`` with an ``"architect"`` or ``"architecture"`` key that
          itself contains ``"tech_stack"``.
        * A JSON ``str`` — parsed and retried recursively.
        * An object with a ``.content`` attribute (e.g. StageArtifact) —
          ``.content`` is treated as a JSON string and retried.
        * An object with a ``.tech_stack`` attribute.

        Returns an empty dict (which causes the registry to fall back to
        ``python_fastapi``) on any failure.

        This method NEVER raises.
        """
        try:
            # ---- StageArtifact / any object with .content -------------------
            content_attr = getattr(context, "content", None)
            if content_attr is not None:
                return self._extract_tech_stack(content_attr)

            # ---- Plain dict -------------------------------------------------
            if isinstance(context, dict):
                # Shape 1: the dict IS already a tech_stack
                # (has language-role keys at top level)
                if any(k in context for k in ("backend", "frontend", "database")):
                    return context

                # Shape 2: {"tech_stack": {...}}
                ts = context.get("tech_stack")
                if isinstance(ts, dict):
                    return ts
                if isinstance(ts, str):
                    return {"backend": ts}

                # Shape 3: nested under "architect" / "architecture"
                for nesting_key in ("architect", "architecture"):
                    nested = context.get(nesting_key)
                    if isinstance(nested, dict):
                        ts = nested.get("tech_stack")
                        if isinstance(ts, dict):
                            return ts
                        if isinstance(ts, str):
                            return {"backend": ts}
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

            # ---- JSON string ------------------------------------------------
            if isinstance(context, str):
                try:
                    parsed = json.loads(context)
                    if isinstance(parsed, dict):
                        return self._extract_tech_stack(parsed)
                except (ValueError, TypeError):
                    pass
                return {}

            # ---- Object with .tech_stack attribute --------------------------
            ts_attr = getattr(context, "tech_stack", None)
            if isinstance(ts_attr, dict):
                return ts_attr

        except Exception:  # noqa: BLE001
            pass

        return {}

    def _extract_project_type(self, context: object) -> str | None:
        """Extract project_type from context.

        Handles the same context shapes as _extract_tech_stack.
        Returns the project_type string or None if not found.
        """
        try:
            # ---- StageArtifact / any object with .content -------------------
            content_attr = getattr(context, "content", None)
            if content_attr is not None:
                return self._extract_project_type(content_attr)

            # ---- Plain dict -------------------------------------------------
            if isinstance(context, dict):
                # Direct project_type at top level
                pt = context.get("project_type")
                if isinstance(pt, str):
                    return pt
                # In non_functional_requirements (from Architect output)
                nfr = context.get("non_functional_requirements")
                if isinstance(nfr, dict):
                    pt = nfr.get("project_type")
                    if isinstance(pt, str):
                        return pt
                # Nested under architect/architecture
                for nesting_key in ("architect", "architecture"):
                    nested = context.get(nesting_key)
                    if isinstance(nested, dict):
                        pt = nested.get("project_type")
                        if isinstance(pt, str):
                            return pt
                        nfr = nested.get("non_functional_requirements")
                        if isinstance(nfr, dict):
                            pt = nfr.get("project_type")
                            if isinstance(pt, str):
                                return pt
                    elif isinstance(nested, str):
                        try:
                            parsed_nested = json.loads(nested)
                            if isinstance(parsed_nested, dict):
                                pt = parsed_nested.get("project_type")
                                if isinstance(pt, str):
                                    return pt
                                nfr = parsed_nested.get("non_functional_requirements")
                                if isinstance(nfr, dict):
                                    pt = nfr.get("project_type")
                                    if isinstance(pt, str):
                                        return pt
                        except (ValueError, TypeError):
                            pass

            # ---- JSON string ------------------------------------------------
            if isinstance(context, str):
                try:
                    parsed = json.loads(context)
                    if isinstance(parsed, dict):
                        return self._extract_project_type(parsed)
                except (ValueError, TypeError):
                    pass

        except Exception:  # noqa: BLE001
            pass

        return None

    def _get_backend_prefixes_for_project_type(self, project_type: str | None) -> tuple[str, ...] | None:
        """Map project_type to backend path prefixes.

        Returns a tuple of path prefixes (e.g., ("backend/", "shared/")) or
        None if project_type is unknown (meaning: allow all paths).
        """
        if project_type is None:
            return None

        pt = project_type.lower().strip()

        # Python/FastAPI/Django/Flask → backend/
        if pt in ("python", "fastapi", "django", "flask", "web_fullstack", "api_service", "web_backend"):
            return ("backend/",)

        # Mobile/React Native/Expo → app/ (no backend/ prefix in RN)
        if pt in ("mobile_app", "mobile", "react_native", "expo", "android", "ios"):
            return ("app/", "src/")

        # Go → cmd/, internal/, pkg/
        if pt in ("go", "golang"):
            return ("cmd/", "internal/", "pkg/")

        # Rust → src/
        if pt in ("rust", "cargo"):
            return ("src/",)

        # Kotlin/Android → app/src/
        if pt in ("kotlin", "android"):
            return ("app/src/",)

        # Java/Spring → src/main/java/
        if pt in ("java", "spring", "spring_boot"):
            return ("src/main/java/",)

        # ML Pipeline → src/, pipelines/
        if pt in ("ml_pipeline", "ml", "machine_learning"):
            return ("src/", "pipelines/")

        # CLI Tool → src/, cmd/
        if pt in ("cli_tool", "cli"):
            return ("src/", "cmd/")

        # Data Pipeline → src/, pipelines/
        if pt in ("data_pipeline", "etl"):
            return ("src/", "pipelines/")

        # Library → src/, lib/
        if pt in ("library", "lib"):
            return ("src/", "lib/")

        # Unknown project type → allow all (return None)
        return None

    # ------------------------------------------------------------------
    # Sprint execution
    # ------------------------------------------------------------------

    def execute_sprint(
        self, project_id: str, file_plan: FilePlan, context: object | None = None
    ) -> SprintExecutionResult:
        """Execute all backend files in this sprint.

        Language profile is resolved *once* at sprint start — preferring
        ``file_plan.tech_stack`` (most reliable) then falling back to ``context``.
        The resolved profile is passed to every :meth:`_generate_one_file` call so
        the system prompt and default language stay consistent across all files in
        the same sprint.

        When ``SPRINT_PARALLEL_FILES > 1``, files with satisfied dependencies are
        dispatched concurrently in waves.  The sequential path
        (``SPRINT_PARALLEL_FILES ≤ 1`` or unset) is byte-for-byte identical to the
        original implementation — no regression.
        """
        # Resolve profile ONCE for the entire sprint.
        # Priority: file_plan.tech_stack (already architect-approved) → context
        _resolve_src: object = getattr(file_plan, "tech_stack", None) or context
        profile = self._resolve_language_profile(_resolve_src)

        gen_order = getattr(file_plan, "generation_order", []) or []
        files_map = getattr(file_plan, "files", {}) or {}

        # Read folder structure from blueprint to determine backend paths dynamically.
        # Falls back to the old "backend/" prefix if no blueprint is available.
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
            _backend_paths = tuple(
                node["path"].rstrip("/")
                for node in _bp.get("folder_structure", [])
                if isinstance(node, dict) and node.get("owner") in ("backend", "shared")
            )
            if _backend_paths:
                backend_files = [
                    fp for fp in gen_order
                    if any(fp.startswith(p) for p in _backend_paths)
                ]
                if not backend_files and files_map:
                    backend_files = [
                        fp for fp in files_map
                        if any(fp.startswith(p) for p in _backend_paths)
                    ]
            else:
                backend_files = list(gen_order) or list(files_map.keys())
            logger.info(
                "[BackendAgent] blueprint folder filter: paths=%s files=%d project=%s",
                _backend_paths, len(backend_files), project_id,
            )
        else:
            project_type = self._extract_project_type(context)
            _backend_prefixes = self._get_backend_prefixes_for_project_type(project_type)

            if _backend_prefixes is None:
                logger.warning(
                    "[BackendAgent] no blueprint found and unknown project_type=%s — allowing all paths: project=%s",
                    project_type, project_id,
                )
                backend_files = list(gen_order) or list(files_map.keys())
            else:
                logger.info(
                    "[BackendAgent] no blueprint found — using project_type=%s prefixes=%s: project=%s",
                    project_type, _backend_prefixes, project_id,
                )
                backend_files = [
                    fp for fp in gen_order
                    if any(fp.startswith(p) for p in _backend_prefixes)
                ]
                if not backend_files and files_map:
                    backend_files = [
                        fp for fp in files_map
                        if any(fp.startswith(p) for p in _backend_prefixes)
                    ]

        max_workers = int(os.getenv("SPRINT_PARALLEL_FILES", "1"))

        if max_workers <= 1 or len(backend_files) <= 1:
            # ── Sequential path — original behaviour, no regression ───────────
            written_files: list[FileGenerationResult] = []
            failed_files: list[FileGenerationResult] = []

            for file_path in backend_files:
                # Default language comes from the resolved profile, not hardcoded "python"
                file_spec = files_map.get(file_path) or FileSpec(
                    file_path=file_path, language=profile.language
                )
                result = self._generate_one_file(
                    project_id=project_id,
                    file_path=file_path,
                    file_spec=file_spec,
                    file_plan=file_plan,
                    context=context,
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
                "BackendDeveloperAgent: parallel sprint execution: "
                "files=%d max_workers=%d",
                len(backend_files), max_workers,
            )
            written_files, failed_files = self._execute_sprint_parallel(
                project_id=project_id,
                file_list=backend_files,
                files_map=files_map,
                file_plan=file_plan,
                context=context,
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
        profile: LanguageProfile,
        max_workers: int,
    ) -> tuple[list[FileGenerationResult], list[FileGenerationResult]]:
        """Execute file generation in dependency-ordered waves.

        Algorithm
        ---------
        A file is "ready" when every entry in its ``depends_on`` list is either:

        * already in ``completed`` (successfully written in a prior wave), or
        * not in ``file_list`` at all (external / pre-existing file, treated as
          unconditionally available).

        Each wave collects all currently-ready files and runs them concurrently
        inside a :class:`~concurrent.futures.ThreadPoolExecutor`.
        ``_index_file_if_available()`` is called immediately after each file is
        written so subsequent waves have up-to-date symbol data.

        Failures
        --------
        A failed file is recorded and the rest of its wave continues unblocked.
        Files that depend on a failed file are never scheduled (their dependency
        will never enter ``completed``) and are reported as orphaned at the end.

        Thread safety
        -------------
        ``_generate_one_file`` writes only to its own ``file_path``.  The
        ``scheduled`` set guarantees every path appears in at most one wave, so no
        two workers ever race on the same output file.  ``ProjectSymbolIndex`` is
        guarded by an ``RLock`` internally — no extra locking is needed here.

        Parameters
        ----------
        file_list:
            Ordered list of ``backend/…`` paths (respects ``generation_order``).
        files_map:
            ``{file_path: FileSpec}`` from the file plan.
        max_workers:
            Maximum concurrent threads per wave (from ``SPRINT_PARALLEL_FILES``).

        Returns
        -------
        (written_files, failed_files)
        """
        written_files: list[FileGenerationResult] = []
        failed_files: list[FileGenerationResult] = []

        completed: set[str] = set()   # paths generated successfully
        failed: set[str] = set()      # paths that failed (recorded for logging)
        scheduled: set[str] = set()   # deduplication guard — each path at most once

        all_file_set: set[str] = set(file_list)

        # Protects list appends across concurrent worker threads.
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
                profile=profile,
            )

        wave_number = 0
        while True:
            # Build the next wave: every unscheduled file whose deps are satisfied.
            wave: list[str] = []
            for fp in file_list:
                if fp in scheduled:
                    continue
                file_spec = files_map.get(fp)
                deps: list[str] = (
                    (getattr(file_spec, "depends_on", None) or []) if file_spec else []
                )
                # A dep is satisfied when it was successfully written OR when it
                # is not in our file list (pre-existing / external dependency).
                if all(d in completed or d not in all_file_set for d in deps):
                    wave.append(fp)

            if not wave:
                # No more ready files — either done, or remaining files are orphaned
                # because their upstream dep failed and will never enter `completed`.
                break

            wave_number += 1
            scheduled.update(wave)
            logger.info(
                "BackendDeveloperAgent: wave %d — %d file(s): %s",
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
                            "BackendDeveloperAgent: unexpected exception generating %s: %s",
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
                            "BackendDeveloperAgent: wave %d done: %s", wave_number, fp,
                        )
                    else:
                        failed.add(fp)
                        logger.error(
                            "BackendDeveloperAgent: wave %d failed: %s after %d attempts",
                            wave_number, fp, self.MAX_ATTEMPTS_PER_FILE,
                        )
                        with _results_lock:
                            failed_files.append(result)

        # Files never scheduled: their deps never all completed (upstream failure).
        orphaned = [fp for fp in file_list if fp not in scheduled]
        for fp in orphaned:
            logger.warning(
                "BackendDeveloperAgent: skipping %s — "
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
            "BackendDeveloperAgent: parallel sprint done — "
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

        Thread safety: ``ProjectSymbolIndex`` is guarded by an ``RLock`` internally
        — no additional locking is needed at this call site.

        Parameters
        ----------
        project_id:
            Active project identifier.
        file_path:
            Repo-relative path of the file just written (e.g.
            ``"backend/app/models/user.py"``).
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
    ) -> FileGenerationResult:
        """Generate, validate, and write ONE file.

        Parameters
        ----------
        profile:
            The language profile resolved for this sprint.  Determines both the
            LLM system prompt and the fallback language for validation.
        """
        last_error = ""

        for attempt in range(1, self.MAX_ATTEMPTS_PER_FILE + 1):
            prompt = self._build_file_prompt(
                file_spec=file_spec,
                file_plan=file_plan,
                project_id=project_id,
                previous_error=last_error,
                attempt=attempt,
                context=context,
            )

            response = self.llm_manager.generate_text(
                prompt=prompt,
                system_prompt=self._file_system_prompt(profile),
                stage="backend",
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
        self, file_spec: FileSpec, file_plan: FilePlan, project_id: str, previous_error: str, attempt: int,
        sprint_brief: str = "", context: object | None = None,
    ) -> str:
        """Build prompt for ONE file generation.

        FIX 5: Uses FileIndexer summaries for large dependency files instead of
        sending full file content, preventing context window overflow on large projects.

        Now also injects context sections: architect summary, API contracts, predecessor message.
        """
        _FULL_CONTENT_THRESHOLD = 1500
        dependency_context = ""
        deps = getattr(file_spec, "depends_on", []) or []
        for dep_path in deps[:3]:
            dep_content = self.project_writer.read_file(project_id, dep_path)
            if dep_content and len(dep_content) <= _FULL_CONTENT_THRESHOLD:
                # Small file — send full content
                dependency_context += f"\n\n# {dep_path}:\n{dep_content}"
            elif self._file_indexer is not None:
                # Large file — send compact summary from FileIndexer
                summary = self._file_indexer.get_file_summary(project_id, dep_path)
                if summary:
                    dependency_context += f"\n\n# {dep_path} (summary — file too large for full context):\n{summary}"
            elif dep_content:
                # No FileIndexer — truncate
                dependency_context += f"\n\n# {dep_path} (first 1500 chars):\n{dep_content[:1500]}"

        error_context = ""
        if previous_error:
            error_context = f"\nPREVIOUS ATTEMPT FAILED WITH THESE ERRORS:\n{previous_error}\nFix these errors in your response.\n"

        req_imports = "\n".join(f"  - {imp}" for imp in (getattr(file_spec, "required_imports", []) or []))

        # Extract context sections
        context_sections = ""
        if context is not None:
            try:
                import json as _json
                ctx_dict = {}
                if isinstance(context, str):
                    ctx_dict = _json.loads(context)
                elif isinstance(context, dict):
                    ctx_dict = context
                elif hasattr(context, "content"):
                    ctx_dict = _json.loads(context.content) if isinstance(context.content, str) else {}

                if ctx_dict:
                    parts = []
                    # Architect summary
                    arch_summary = ctx_dict.get("architect") or ctx_dict.get("architecture")
                    if arch_summary:
                        if isinstance(arch_summary, str):
                            try:
                                arch_summary = _json.loads(arch_summary)
                            except Exception:
                                pass
                        if isinstance(arch_summary, dict):
                            summary_text = arch_summary.get("summary") or arch_summary.get("approach") or str(arch_summary)[:2000]
                            parts.append(f"### ARCHITECT SUMMARY\n{summary_text}")

                    # API contracts
                    api_contracts = ctx_dict.get("api_endpoints") or ctx_dict.get("api_design")
                    if api_contracts:
                        if isinstance(api_contracts, str):
                            try:
                                api_contracts = _json.loads(api_contracts)
                            except Exception:
                                pass
                        parts.append(f"### API CONTRACTS\n{_json.dumps(api_contracts, indent=2)[:3000]}")

                    # Predecessor message (from workflow message key)
                    pred_msg = ctx_dict.get("predecessor_message") or ctx_dict.get("previous_stage_output")
                    if pred_msg:
                        parts.append(f"### PREDECESSOR MESSAGE\n{pred_msg[:2000]}")

                    if parts:
                        context_sections = "\n\n" + "\n\n".join(parts) + "\n"
            except Exception:
                pass

        sprint_context = f"{sprint_brief}\n\n" if sprint_brief else ""
        return f"""{sprint_context}Generate the file: {file_spec.file_path}

Purpose: {file_spec.purpose}
Language: {file_spec.language}
Tech stack: {file_plan.tech_stack}

Required imports (must include all of these):
{req_imports}

Required classes to implement:
{file_spec.required_classes}

Required functions to implement:
{file_spec.required_functions}

Exports from this file:
{file_spec.exports}

These dependency files already exist (for context):
{dependency_context}
{error_context}
Write ONLY the complete {file_spec.file_path} file.
No explanation. No markdown. No code fences. Just the code.
"""

    def _file_system_prompt(self, profile: LanguageProfile) -> str:
        """Return the LLM system prompt for code generation using BackendPromptBuilder.

        Uses the generic system prompt from BackendPromptBuilder; the resolved
        technology profile (language, framework, etc.) is injected into the
        user prompt via _build_file_prompt() so the LLM receives it in context.
        """
        return BackendPromptBuilder.SYSTEM_PROMPT

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
