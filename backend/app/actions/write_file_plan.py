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

# DevOps infrastructure files for web projects (containerised deployments).
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
    {"path": "app.json",                    "module": "expo",     "purpose": "Expo app configuration",              "responsible_stage": "devops", "operation": "create"},
    {"path": "eas.json",                    "module": "expo",     "purpose": "Expo Application Services build config", "responsible_stage": "devops", "operation": "create"},
    {"path": "babel.config.js",             "module": "expo",     "purpose": "Babel preset for Expo",              "responsible_stage": "devops", "operation": "create"},
    {"path": "metro.config.js",             "module": "expo",     "purpose": "Metro bundler configuration",         "responsible_stage": "devops", "operation": "create"},
    {"path": ".github/workflows/ci.yml",    "module": "ci",       "purpose": "GitHub Actions CI via expo-github-action", "responsible_stage": "devops", "operation": "create"},
]

# Backward-compat alias used elsewhere in this file
_DEVOPS_FILES = _WEB_DEVOPS_FILES


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
        # Phase 8: FileRegistry is optional — Sprint 1 has no prior files; Sprint 2+ has them.
        self.file_registry = file_registry

    def run(self, context: object, llm: object):
        project_id = getattr(context, "project_id", "") or ""
        base_content = getattr(context, "content", "") or ""
        architecture = self._load_architecture(project_id)
        approved_design = self._load_approved_design(project_id)

        # Store architecture on self so _parse_structured can use it for the
        # deterministic fallback when the LLM returns an empty file list.
        self._last_architecture = architecture

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
        enriched = "\n\n".join(parts)
        return super().run(SimpleNamespace(content=enriched), llm)

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
        """Build a minimal deterministic file plan from the stored architecture.

        Used when the LLM returns an empty file list. Derives one file per
        architecture module (backend/frontend classification from module.layer),
        adds standard entry points, and always includes the required DevOps
        infrastructure files.
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

        # Determine tech stack and project type
        project_type  = (arch.project_type or "web_fullstack").lower()
        stack = arch.tech_stack or {}
        backend_tech  = (stack.get("backend", "")     or "").lower()
        frontend_tech = (stack.get("frontend", "")    or "").lower()
        storage_tech  = (stack.get("storage", "")     or "").lower()
        mobile_tech   = (stack.get("mobile", "")      or "").lower()
        ml_framework  = (stack.get("ml_framework", "") or "").lower()
        serving_tech  = (stack.get("serving", "")     or "").lower()
        language      = (stack.get("language", "")    or "").lower()

        is_python        = "python" in language or any(kw in backend_tech for kw in ("python", "fastapi", "flask", "django"))
        is_node          = any(kw in backend_tech for kw in ("node", "express", "nest"))
        is_react_native  = project_type == "mobile_app" or any(kw in frontend_tech for kw in ("react native", "react-native", "expo"))
        is_flutter       = "flutter" in frontend_tech or "flutter" in mobile_tech
        is_react_web     = "react" in frontend_tech and not is_react_native
        is_no_backend    = any(kw in backend_tech for kw in ("none", "client", "no backend"))
        is_ml_pipeline   = project_type == "ml_pipeline" or bool(ml_framework)
        is_cli_tool      = project_type == "cli_tool"

        # ── ML pipeline: generate training/inference scripts ──────────────────
        if is_ml_pipeline:
            _add("train.py",         "training",  "Main training script",                 "backend")
            _add("evaluate.py",      "eval",      "Model evaluation and metrics",          "backend")
            _add("predict.py",       "inference", "Inference on new data",                 "backend")
            _add("src/model.py",     "model",     "Model architecture definition",         "backend")
            _add("src/dataset.py",   "data",      "Data loading and preprocessing",        "backend")
            _add("src/trainer.py",   "trainer",   "Training loop",                         "backend")
            _add("src/config.py",    "config",    "Hyperparameters and settings",          "backend")
            _add("src/utils.py",     "utils",     "Shared helpers and utilities",          "backend")
            _add("requirements.txt", "deps",      "Python dependencies",                   "devops")
            _add(".github/workflows/ci.yml", "ci", "CI: install deps + run tests",        "devops")
            if "fastapi" in serving_tech or "flask" in serving_tech:
                _add("api/main.py",    "api",  "Inference API server", "backend")
                _add("api/schemas.py", "api",  "Request/response schemas", "backend")
            if "mlflow" in (stack.get("tracking", "") or "").lower():
                _add("src/tracking.py", "tracking", "MLflow experiment logging", "backend")
            return files  # ML pipeline is done — no frontend, no Docker-compose

        # ── CLI tool ──────────────────────────────────────────────────────────
        if is_cli_tool:
            _add("cli/main.py",     "cli",    "CLI entry point",           "backend")
            _add("cli/commands.py", "cli",    "Subcommand implementations","backend")
            _add("cli/config.py",   "config", "Configuration management",  "backend")
            _add("setup.py",        "pkg",    "Package setup",             "devops")
            _add("requirements.txt","deps",   "Python dependencies",       "devops")
            _add(".github/workflows/ci.yml", "ci", "CI pipeline",         "devops")
            return files  # CLI done

        # Component file extension: .tsx for TypeScript-first mobile, .jsx for web React
        ext = ".tsx" if (is_react_native or is_flutter) else ".jsx"

        # Derive files from architecture modules
        for mod in arch.modules:
            layer = (mod.layer or "").lower()
            name = (mod.name or "module").lower().replace(" ", "_")
            purpose = mod.purpose or f"{mod.name} module"

            if "front" in layer or "ui" in layer or "presentation" in layer or "screen" in layer:
                stage = "frontend"
                if is_react_native:
                    _add(f"src/screens/{mod.name}{ext}", name, purpose, stage)
                elif is_react_web:
                    _add(f"src/components/{mod.name}.jsx", name, purpose, stage)
                else:
                    _add(f"src/{name}.js", name, purpose, stage)

            elif "data" in layer or "database" in layer or "persistence" in layer or "storage" in layer:
                if is_react_native:
                    # Mobile storage = TypeScript utility, not a DB model
                    _add(f"src/storage/{name}.ts", name, purpose, "frontend")
                elif is_python:
                    _add(f"app/models/{name}.py", name, purpose, "backend")
                else:
                    _add(f"src/models/{name}.js", name, purpose, "backend")

            else:
                # Logic / service / hook layer
                stage = "frontend" if (is_react_native and is_no_backend) else "backend"
                if mod.files:
                    for f in mod.files[:3]:
                        clean = f.lstrip("/").replace("\\", "/")
                        _add(clean, name, purpose, stage)
                else:
                    if is_react_native:
                        # Mobile logic lives in hooks or utils
                        if "hook" in name or "use" in name:
                            _add(f"src/hooks/{name}.ts", name, purpose, "frontend")
                        else:
                            _add(f"src/utils/{name}.ts", name, purpose, "frontend")
                    elif is_python:
                        _add(f"app/{name}.py", name, purpose, "backend")
                    elif is_node:
                        _add(f"src/{name}.js", name, purpose, "backend")
                    else:
                        _add(f"src/{name}.py", name, purpose, "backend")

        # Always include at least one entry point
        if is_react_native:
            if not any(f["responsible_stage"] == "frontend" for f in files):
                _add("App.tsx",                    "app",     "Root Expo component",               "frontend")
                _add("src/screens/MainScreen.tsx", "screen",  "Main calculator screen",            "frontend")
                _add("src/utils/calculator.ts",    "calc",    "Expression parser and evaluator",   "frontend")
                _add("src/hooks/useCalculator.ts", "hook",    "Calculator state hook",             "frontend")
                _add("src/storage/history.ts",     "storage", "AsyncStorage history persistence",  "frontend")
        elif is_flutter:
            _add("lib/main.dart",         "main",  "Flutter app entry point",   "frontend")
            _add("lib/screens/home.dart", "home",  "Home screen",               "frontend")
        else:
            if not any(f["responsible_stage"] == "backend" for f in files):
                if is_python:
                    _add("app/main.py",  "main", "Application entry point", "backend")
                else:
                    _add("src/index.js", "main", "Application entry point", "backend")

            if not any(f["responsible_stage"] == "frontend" for f in files):
                if is_react_web:
                    _add("src/App.jsx",    "app",   "Root React component", "frontend")
                    _add("src/index.jsx",  "index", "Frontend entry point", "frontend")
                    _add("src/index.html", "html",  "HTML template",        "frontend")
                else:
                    _add("src/index.html", "index", "Frontend entry point", "frontend")
                    _add("src/styles.css", "style", "Application styles",   "frontend")

        # Add platform-appropriate DevOps infrastructure files
        devops_files = _MOBILE_DEVOPS_FILES if (is_react_native or is_flutter) else _WEB_DEVOPS_FILES
        for devops_file in devops_files:
            _add(devops_file["path"], devops_file["module"], devops_file["purpose"], devops_file["responsible_stage"])

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
