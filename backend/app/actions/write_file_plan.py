from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from ..artifact.manager import ArtifactManager
from ..execution.exceptions import SchemaValidationError
from ..prompt.file_plan_builder import FilePlanPromptBuilder
from ..shared.enums.stage import Stage
from ..shared.schemas.architecture_schema import ArchitectureArtifact
from ..shared.schemas.file_plan_schema import FilePlanArtifact
from ..workspace.file_registry import FileRegistry
from .architecture_summary import summarize_architecture
from .base_action import LLMAction

logger = logging.getLogger(__name__)

# Maps generic LLM-generated module names to idiomatic Python/JS file names.
# When the model names a module "BusinessModule" or "InfrastructureModule" the
# resulting file paths (businessmodule.py, infrastructuremodule.py) are
# meaningless to a developer. This table maps the de-suffixed, lowercase form
# to the conventional file name used in real projects.
_MODULE_NAME_CANONICAL: dict[str, str] = {
    # Business / service layer
    "business": "service",
    "businessmodule": "service",
    "businesslogic": "service",
    "service": "service",
    "servicemodule": "service",
    "services": "service",
    # Infrastructure / config
    "infrastructure": "config",
    "infrastructuremodule": "config",
    "infra": "config",
    "inframodule": "config",
    "configuration": "config",
    # Presentation / UI
    "presentation": "views",
    "presentationmodule": "views",
    "ui": "views",
    "uimodule": "views",
    "view": "views",
    "viewmodule": "views",
    # API / Routes
    "api": "routes",
    "apimodule": "routes",
    "route": "routes",
    "routemodule": "routes",
    "routes": "routes",
    "endpoint": "routes",
    # Core / main
    "core": "core",
    "coremodule": "core",
    "backend": "main",
    "backendmodule": "main",
    "application": "main",
    "app": "main",
    # Data / Models (handled by layer check, but normalized here too)
    "data": "models",
    "datamodule": "models",
    "database": "database",
    "databasemodule": "database",
    "persistence": "database",
    "storage": "storage",
    # Auth
    "auth": "auth",
    "authmodule": "auth",
    "authentication": "auth",
    "authorization": "auth",
    # Frontend / UI components
    "frontend": "app",
    "frontendmodule": "app",
    # Queue / cache
    "queue": "tasks",
    "queuemodule": "tasks",
    "cache": "cache",
    "cachemodule": "cache",
}


def _canonical_module_name(raw: str) -> str:
    """Convert a generic LLM module name to an idiomatic Python/JS file stem.

    Examples
    --------
    "BusinessModule" → "service"
    "InfrastructureModule" → "config"
    "DataModule" → "models"
    "UserAuthModule" → "auth"
    "PresentationModule" → "views"
    """
    key = raw.lower().replace(" ", "").replace("_", "").replace("-", "")
    # Direct lookup
    if key in _MODULE_NAME_CANONICAL:
        return _MODULE_NAME_CANONICAL[key]
    # Strip common suffixes and try again
    for suffix in ("module", "layer", "manager", "handler", "component"):
        if key.endswith(suffix) and len(key) > len(suffix):
            stem = key[: -len(suffix)]
            if stem in _MODULE_NAME_CANONICAL:
                return _MODULE_NAME_CANONICAL[stem]
    # "routes" / "service" suffixes: keep as-is (they're already idiomatic)
    if key.endswith("routes"):
        return "routes"
    if key.endswith("service") and not key == "service":
        return key  # e.g. userservice → userservice (fine)
    # Fallback: lowercase_underscored version of the raw name
    return raw.lower().replace(" ", "_").replace("-", "_")


# DevOps infrastructure files for containerised web / API projects.
# Written by the DevOps stage, so responsible_stage="devops".
_WEB_DEVOPS_FILES = [
    {"path": "Dockerfile",                  "module": "docker",   "purpose": "Container image for the app",         "responsible_stage": "devops", "operation": "create"},
    {"path": "docker-compose.yml",          "module": "docker",   "purpose": "Local development stack",             "responsible_stage": "devops", "operation": "create"},
    {"path": ".dockerignore",               "module": "docker",   "purpose": "Files to exclude from Docker image",  "responsible_stage": "devops", "operation": "create"},
    {"path": ".github/workflows/ci.yml",    "module": "ci",       "purpose": "GitHub Actions CI pipeline",          "responsible_stage": "devops", "operation": "create"},
]

# DevOps infrastructure files for mobile / Expo projects.
# No Docker — mobile apps are distributed via app stores, not containers.
_MOBILE_DEVOPS_FILES = [
    {"path": "app.json",                    "module": "expo",     "purpose": "Expo / React Native app configuration", "responsible_stage": "devops", "operation": "create"},
    {"path": "eas.json",                    "module": "expo",     "purpose": "Expo Application Services build config", "responsible_stage": "devops", "operation": "create"},
    {"path": "babel.config.js",             "module": "expo",     "purpose": "Babel preset for Expo/React Native",  "responsible_stage": "devops", "operation": "create"},
    {"path": "metro.config.js",             "module": "expo",     "purpose": "Metro bundler configuration",         "responsible_stage": "devops", "operation": "create"},
    {"path": ".github/workflows/ci.yml",    "module": "ci",       "purpose": "GitHub Actions CI for mobile",        "responsible_stage": "devops", "operation": "create"},
]

# Minimal devops for non-containerised project types (cli_tool, library,
# ml_pipeline, data_pipeline).  No Docker — these projects are installed via
# pip/npm or run directly; a Dockerfile would be misleading overhead.
_MINIMAL_DEVOPS_FILES = [
    {"path": ".github/workflows/ci.yml",    "module": "ci",       "purpose": "GitHub Actions CI pipeline",          "responsible_stage": "devops", "operation": "create"},
]

# Project types that do NOT need Docker in their devops baseline.
_NON_CONTAINER_PROJECT_TYPES = frozenset({
    "cli_tool", "library", "ml_pipeline", "data_pipeline",
})

# Backward-compat alias used elsewhere in this file
_DEVOPS_FILES = _WEB_DEVOPS_FILES


def _derive_fallback_path(
    layer: str,
    name: str,
    language: str,
    backend_tech: str,
    frontend_tech: str,
) -> str:
    """Derive a single reasonable file path when ModuleSpec.files is empty.

    Applies language/tech signals in order:
      1. Kotlin / Android → .kt in the conventional package dir
      2. Swift / iOS       → .swift in Sources/
      3. Go                → .go in the package dir
      4. Rust              → .rs in src/
      5. Python            → .py in app/
      6. Node / JS         → .js in src/
      7. Fallback          → .py in src/

    This function is a safety net — the primary source of truth is always
    ModuleSpec.files populated by the Architect.
    """
    is_kotlin  = "kotlin"  in language or "android" in backend_tech or "android" in layer
    is_swift   = "swift"   in language or "ios"     in backend_tech
    is_go      = "go"      in language or "gin"     in backend_tech or "go"  in backend_tech
    is_rust    = "rust"    in language or "actix"   in backend_tech or "axum" in backend_tech
    is_python  = "python"  in language or any(kw in backend_tech for kw in ("fastapi", "flask", "django", "python"))
    is_node    = any(kw in backend_tech for kw in ("node", "express", "nest", "javascript", "typescript"))
    is_frontend_layer = any(kw in layer for kw in ("front", "ui", "screen", "view", "presentation"))

    if is_kotlin:
        pkg = "com/app"
        return f"app/src/main/java/{pkg}/{name.capitalize()}.kt"
    if is_swift:
        return f"Sources/{name.capitalize()}.swift"
    if is_go:
        return f"internal/{name}/{name}.go"
    if is_rust:
        return f"src/{name}.rs"
    if is_frontend_layer:
        if "react" in frontend_tech or "vue" in frontend_tech:
            return f"src/components/{name.capitalize()}.jsx"
        if "flutter" in frontend_tech:
            return f"lib/screens/{name}.dart"
        return f"src/{name}.js"
    if is_python:
        return f"app/{name}.py"
    if is_node:
        return f"src/{name}.js"
    # Unknown stack — default to Python (most common in this codebase)
    return f"src/{name}.py"


def _derive_entry_point(language: str, backend_tech: str, project_type: str) -> str:
    """Return a language-appropriate application entry point path.

    Called only when the architecture produced no files at all — absolute last resort.
    """
    if "kotlin" in language or "android" in backend_tech:
        return "app/src/main/java/com/app/MainActivity.kt"
    if "swift" in language:
        return "Sources/App/main.swift"
    if "go" in language or "gin" in backend_tech:
        return "cmd/server/main.go"
    if "rust" in language:
        return "src/main.rs"
    if "python" in language or any(kw in backend_tech for kw in ("fastapi", "flask", "django")):
        return "app/main.py"
    if any(kw in backend_tech for kw in ("node", "express", "nest")):
        return "src/index.js"
    return "app/main.py"


class WriteFilePlanAction(LLMAction):
    """FileStructurePlanner's action: produces a structured FilePlanArtifact.

    Runs after Security, so its predecessor-message slot (see
    WorkflowEngine._with_predecessor_message) only carries the SecurityReport
    -- the ArchitectureArtifact is further back in the pipeline and isn't
    covered by that single-slot mechanism. This action fetches it directly
    from ArtifactManager, keyed by the project_id the caller puts on
    context, so the plan is always grounded in the real approved
    architecture instead of whatever text happened to survive to this point.

    Phase 8: also accepts a FileRegistry so Sprint 2+ prompts include the list
    of already-written files, enabling the LLM to set operation="update"/"patch"
    instead of blindly re-creating files.
    """

    name = "WriteFilePlan"
    description = "Turn the approved architecture and design into a concrete, minimal file list."
    schema_model = FilePlanArtifact
    system_prompt = (
        "You are a File Structure Planner. Respond with ONLY a single JSON object (no prose outside it) "
        "with this key: files (list of objects with path/module/purpose/responsible_stage/operation, where "
        "responsible_stage is exactly 'backend' or 'frontend', and operation is exactly 'create', 'update', "
        "or 'patch' — see the EXISTING FILES section in the context for which files already exist). "
        "For 'update' and 'patch' entries also include change_description (what to add/change). "
        "Keep it minimal: one file per real responsibility, not one per class or function."
    )

    def __init__(
        self,
        prompt_builder: FilePlanPromptBuilder | None = None,
        artifact_manager: ArtifactManager | None = None,
        file_registry: FileRegistry | None = None,
    ) -> None:
        """Wire the prompt builder, ArtifactManager (architecture fetch), and optional FileRegistry
        (existing-file list for Sprint 2+ operation assignment)."""
        super().__init__(prompt_builder or FilePlanPromptBuilder())
        self.artifact_manager = artifact_manager or ArtifactManager()
        # Auto-create FileRegistry if none provided — mirrors WriteProjectFilesAction pattern.
        # Without this, self.file_registry stays None and the EXISTING FILES block is never
        # injected into the prompt, so the LLM regenerates the same files every sprint.
        self.file_registry = file_registry or FileRegistry(
            workspace_manager=getattr(self.artifact_manager, "workspace_manager", None)
        )

    def run(self, context: object, llm: object):
        project_id = getattr(context, "project_id", "") or ""
        base_content = getattr(context, "content", "") or ""
        architecture = self._load_architecture(project_id)
        approved_design = self._load_approved_design(project_id)
        sprint_delta = self._load_sprint_delta(project_id)

        # Store architecture on self so _parse_structured can use it for the
        # deterministic fallback when the LLM returns an empty file list.
        self._last_architecture = architecture
        # Store delta on self so _apply_sprint_delta_overrides can use it post-parse.
        self._sprint_delta = sprint_delta

        parts = [base_content]
        if architecture:
            parts.append(f"### Architecture Summary\n{summarize_architecture(architecture)}")
        if approved_design:
            import json
            # Limit design JSON size to avoid overwhelming small-context models.
            design_str = json.dumps(approved_design, indent=2)
            if len(design_str) > 3000:
                design_str = design_str[:3000] + "\n... (truncated for brevity)"
            parts.append(f"### Approved Design Spec\n```json\n{design_str}\n```")
        # Phase 8: inject existing-file registry so LLM sets operation correctly for Sprint 2+
        if self.file_registry and project_id:
            registry_summary = self.file_registry.to_prompt_summary(project_id)
            if registry_summary:
                parts.append(registry_summary)
        # SprintDeltaPlanner decisions: inject as authoritative operation hints so the
        # LLM knows exactly which files are new vs updated.  After parsing we also
        # override the operations directly (belt-and-suspenders) so LLM drift can't
        # produce a Sprint-2 "create" for a file that already exists.
        if sprint_delta and sprint_delta.decisions:
            delta_lines = ["### Sprint Operation Plan (authoritative — follow exactly)"]
            for d in sprint_delta.decisions[:30]:
                line = f"  {d.operation.upper()}: {d.path}"
                if d.change_description:
                    line += f" — {d.change_description}"
                delta_lines.append(line)
            parts.append("\n".join(delta_lines))
        enriched = "\n\n".join(parts)
        result = super().run(SimpleNamespace(content=enriched), llm)
        # Apply SprintDeltaArtifact decisions as hard overrides on the parsed file list.
        # This is the "belt" part — even if the LLM ignored the hint above, the
        # operation field in the final artifact will be correct.
        if sprint_delta and sprint_delta.decisions and result.structured:
            self._apply_sprint_delta_overrides(result.structured, sprint_delta)
        return result

    def _load_sprint_delta(self, project_id: str):
        """Load SprintDeltaArtifact produced by SprintDeltaPlanner, or None."""
        if not project_id or self.artifact_manager is None:
            return None
        try:
            from ..shared.enums.stage import Stage
            from ..shared.schemas.sprint_delta_schema import SprintDeltaArtifact
            art = self.artifact_manager.get_artifact(project_id, Stage.SprintDelta)
            if not art or not art.structured_content:
                return None
            return SprintDeltaArtifact.model_validate(art.structured_content)
        except Exception as exc:
            logger.debug("WriteFilePlanAction: sprint delta load failed: %s", exc)
            return None

    @staticmethod
    def _apply_sprint_delta_overrides(structured: dict, sprint_delta) -> None:
        """Override operation/change_description in parsed file list from SprintDeltaArtifact.

        Belt-and-suspenders: even if the LLM ignored the operation hint injected
        into the prompt, this ensures the final FilePlanArtifact has correct
        operations for every file the SprintDeltaPlanner explicitly decided on.
        """
        decision_map = {d.path: d for d in sprint_delta.decisions}
        files = structured.get("files") or []
        for f in files:
            if not isinstance(f, dict):
                continue
            path = f.get("path", "")
            decision = decision_map.get(path)
            if decision:
                f["operation"] = decision.operation
                if decision.change_description:
                    f["change_description"] = decision.change_description

    def _parse_structured(self, text: str) -> dict[str, Any]:
        """Parse LLM response into FilePlanArtifact schema.

        When the LLM returns an empty file list (common with vision-language
        models like qwen3-vl that are not optimised for structured code
        planning), we fall back to a deterministic plan derived from the
        architecture artifact rather than retrying endlessly. Retries produce
        the same empty result because the model limitation is structural, not
        prompt-related.
        """
        parsed = super()._parse_structured(text)

        # Normalise: LLM sometimes returns a bare list instead of {"files": [...]}
        if not parsed and text.strip().startswith("["):
            import json
            try:
                items = json.loads(text.strip())
                if isinstance(items, list):
                    parsed = {"files": items}
            except Exception:
                pass

        files = parsed.get("files") if parsed else None
        if files:
            return parsed

        # LLM returned empty — generate deterministic fallback from architecture.
        logger.warning(
            "WriteFilePlan: LLM returned empty file list. "
            "Generating deterministic fallback from architecture artifact. "
            "Raw response: %s",
            (text or "")[:200],
        )
        fallback = self._build_fallback_plan()
        if fallback:
            logger.info("WriteFilePlan: fallback generated %d files", len(fallback))
            return {"files": fallback}

        # Architecture also unavailable — nothing we can do.
        raise SchemaValidationError(
            "File Plan is empty and no architecture is available for fallback. "
            "Ensure the Architect stage completed successfully before running FileStructurePlanner."
        )

    def _build_fallback_plan(self) -> list[dict[str, Any]]:
        """Build a minimal file plan from the stored architecture artifact.

        Design principle: trust the Architect's output rather than maintaining a
        hardcoded if/else tree that can never cover every project type.

        The Architect already knows the tech stack and project type — it populates
        ModuleSpec.files with the correct paths (Kotlin for Android, .py for Python,
        .swift for iOS, etc.).  We read those paths directly.

        For modules whose files list is empty we call _derive_fallback_path() which
        applies a small set of language-aware rules — but only as a last resort.

        A CI file and platform-appropriate devops files are always appended.
        """
        arch: ArchitectureArtifact | None = getattr(self, "_last_architecture", None)
        if arch is None:
            return []

        files: list[dict[str, Any]] = []
        seen: set[str] = set()

        def _add(path: str, module: str, purpose: str, stage: str) -> None:
            if path and path not in seen:
                seen.add(path)
                files.append({
                    "path": path,
                    "module": module,
                    "purpose": purpose,
                    "responsible_stage": stage,
                    "operation": "create",
                })

        # ── Minimal tech-stack signals (only for devops selection) ────────────
        stack         = arch.tech_stack or {}
        project_type  = (arch.project_type or "web_fullstack").lower()
        language      = (stack.get("language", "")    or "").lower()
        backend_tech  = (stack.get("backend", "")     or "").lower()
        frontend_tech = (stack.get("frontend", "")    or "").lower()
        mobile_tech   = (stack.get("mobile", "")      or "").lower()

        is_mobile = (
            project_type == "mobile_app"
            or any(kw in frontend_tech for kw in ("react native", "expo"))
            or any(kw in mobile_tech   for kw in ("android", "ios", "flutter"))
        )

        # ── Phase 1: trust ModuleSpec.files from the Architect ───────────────
        frontend_layers = {"frontend", "ui", "presentation", "screen", "view", "mobile"}
        for mod in arch.modules:
            name    = _canonical_module_name(mod.name or "module")
            purpose = mod.purpose or f"{mod.name} module"
            layer   = (mod.layer or "").lower()
            stage   = "frontend" if layer in frontend_layers else "backend"

            if mod.files:
                # The Architect provided concrete file paths — use them as-is.
                # These are already correct for the project type.
                for f in mod.files[:5]:
                    clean = f.lstrip("/").replace("\\", "/")
                    _add(clean, name, purpose, stage)
            else:
                # Architect gave no files — derive one minimal path from context.
                path = _derive_fallback_path(
                    layer, name, language, backend_tech, frontend_tech
                )
                _add(path, name, purpose, stage)

        # ── Phase 2: ensure at least one entry file exists ───────────────────
        if not any(f["responsible_stage"] in ("backend", "frontend") for f in files):
            entry = _derive_entry_point(language, backend_tech, project_type)
            _add(entry, "main", "Application entry point", "backend")

        # ── Phase 3: CI + platform devops ────────────────────────────────────
        # Three tiers: mobile (no Docker, Expo/RN config), minimal (CI only,
        # for cli/library/ml/data project types), web (Docker + CI).
        _add(".github/workflows/ci.yml", "ci", "CI pipeline", "devops")
        if is_mobile:
            devops_files = _MOBILE_DEVOPS_FILES
        elif project_type in _NON_CONTAINER_PROJECT_TYPES:
            devops_files = _MINIMAL_DEVOPS_FILES
        else:
            devops_files = _WEB_DEVOPS_FILES
        for df in devops_files:
            _add(df["path"], df["module"], df["purpose"], df["responsible_stage"])

        return files

    def _load_approved_design(self, project_id: str) -> dict | None:
        if not project_id:
            return None
        from ..workspace.manager import WorkspaceManager
        ws_mgr = WorkspaceManager()
        return ws_mgr.load_approved_design(project_id)

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
