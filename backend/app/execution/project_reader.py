from __future__ import annotations

import ast
import logging
from pathlib import Path
from ..workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)


class ProjectReader:
    """Reads generated project files from disk.

    Used by QA, DevOps, and Documentation agents to understand what was actually built
    before producing their outputs.
    """

    def __init__(self, workspace_manager: WorkspaceManager | None = None) -> None:
        self.workspace = workspace_manager or WorkspaceManager()

    def get_project_dir(self, project_id: str) -> Path:
        return self.workspace.get_workspace_path(project_id) / "project"

    # Source file extensions to include when reading backend files.
    # Covers Python, TypeScript, JavaScript, and their JSX/TSX variants.
    _SOURCE_EXTENSIONS = frozenset({
        ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    })

    def read_all_backend_files(self, project_id: str) -> dict[str, str]:
        """Returns {relative_path: file_content} for backend source files.

        Reads Python, TypeScript, and JavaScript files from the backend/
        directory (and the project root if no backend/ subdirectory exists).
        Falls back to scanning the whole project dir when backend/ is absent,
        so TypeScript-only and monorepo projects work correctly.

        Truncates individual files over 2000 chars to keep context manageable.
        """
        project_dir = self.get_project_dir(project_id)
        backend_dir = project_dir / "backend"

        # Allow scanning the project root when there is no backend/ subdir
        # (happens with JS/TS projects whose structure has no Python backend).
        scan_dirs = [backend_dir] if backend_dir.exists() else [project_dir]

        files: dict[str, str] = {}
        for scan_dir in scan_dirs:
            for path in sorted(scan_dir.rglob("*")):
                if path.suffix.lower() not in self._SOURCE_EXTENSIONS:
                    continue
                # Skip node_modules, __pycache__, hidden dirs, test files
                parts = path.parts
                if any(p in ("node_modules", "__pycache__", ".git", "venv", ".venv") for p in parts):
                    continue
                rel_path = str(path.relative_to(project_dir)).replace("\\", "/")
                try:
                    content = path.read_text(encoding="utf-8")
                    if len(content) > 2000:
                        content = content[:2000] + "\n// ... [truncated]"
                    files[rel_path] = content
                except Exception as e:
                    logger.warning("Could not read file %s: %s", path, e)

        logger.info("Read %d backend files for project %s", len(files), project_id)
        return files

    def read_file(self, project_id: str, file_path: str) -> str | None:
        """Read a specific project file."""
        full_path = self.get_project_dir(project_id) / file_path
        if full_path.exists() and full_path.is_file():
            try:
                return full_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("Could not read %s: %s", file_path, e)
        return None

    # Directories that are never useful to expose to agents — exclude them from
    # both list_all_files() and any file-content scanning.
    _SKIP_DIRS: frozenset[str] = frozenset({
        "node_modules", "__pycache__", ".git", "venv", ".venv",
        ".expo", ".gradle", ".idea", ".DS_Store", "build", "dist",
        ".pytest_cache", ".ruff_cache", "coverage",
    })

    def list_all_files(self, project_id: str) -> list[str]:
        """List source/config files in the project directory.

        Excludes generated/dependency directories (node_modules, __pycache__,
        .git, venv, build, dist, etc.) so that the returned list stays small
        enough to embed in an LLM prompt without causing context-window overflow.
        A React Native project's node_modules alone can hold 50 000+ files.
        """
        project_dir = self.get_project_dir(project_id)
        if not project_dir.exists():
            return []

        results: list[str] = []
        for p in sorted(project_dir.rglob("*")):
            if not p.is_file():
                continue
            # Skip anything under a blocked directory name at any depth
            if any(part in self._SKIP_DIRS for part in p.parts):
                continue
            name = p.name
            if ".attempt-" in name or "_attempt_" in name:
                continue
            results.append(str(p.relative_to(project_dir)).replace("\\", "/"))
        return results

    def get_api_routes(self, project_id: str) -> list[dict]:
        """Parse router files to extract API endpoints.

        Returns list of {method, path, function_name, file} Used by QA to know what
        endpoints to test.
        """
        routes = []
        backend_files = self.read_all_backend_files(project_id)

        for file_path, content in backend_files.items():
            if "router" not in file_path and "route" not in file_path and "main" not in file_path and "app" not in file_path:
                continue
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        for decorator in node.decorator_list:
                            if isinstance(decorator, ast.Call):
                                if hasattr(decorator.func, "attr"):
                                    method = decorator.func.attr
                                    if method in ["get", "post", "put", "delete", "patch"]:
                                        path = ""
                                        if decorator.args:
                                            try:
                                                path = ast.literal_eval(decorator.args[0])
                                            except Exception as e:
                                                logger.warning(
                                                    "[ProjectReader.get_api_routes] Non-critical failure evaluating route decorator arg in %s: %s",
                                                    file_path,
                                                    str(e),
                                                    exc_info=True,
                                                )
                                                path = ""
                                        routes.append(
                                            {
                                                "method": method.upper(),
                                                "path": str(path),
                                                "function": node.name,
                                                "file": file_path,
                                            }
                                        )
            except Exception as e:
                logger.debug("Could not parse routes from %s: %s", file_path, e)

        return routes

    def get_models(self, project_id: str) -> list[dict]:
        """Parse model files to extract class definitions.

        Only processes Python (.py) files — JS/TS files use a different AST
        and would raise SyntaxError if fed to the Python parser.

        Returns list of {class_name, file} used by QA and DevOps to understand
        the data structure.
        """
        models = []
        backend_files = self.read_all_backend_files(project_id)

        for file_path, content in backend_files.items():
            if "model" not in file_path:
                continue
            # Only attempt Python AST parsing on .py files
            if not file_path.endswith(".py"):
                continue
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        models.append({"class_name": node.name, "file": file_path})
            except Exception as e:
                logger.warning(
                    "[ProjectReader.get_models] Non-critical failure parsing models from %s: %s",
                    file_path,
                    str(e),
                    exc_info=True,
                )

        return models

    def get_requirements_txt(self, project_id: str) -> str | None:
        """Read requirements.txt if it exists."""
        return self.read_file(project_id, "requirements.txt") or self.read_file(project_id, "backend/requirements.txt")

    def get_tech_stack(self, project_id: str) -> dict:
        """Infer tech stack from existing files.

        Used by DevOps and QA to write correct configs and tests.
        Detects mobile (React Native / Expo) vs. web projects.
        """
        files = self.list_all_files(project_id)
        file_set = set(files)

        # Mobile detection signals — checked in priority order.
        # 1. Expo-specific config files on disk
        mobile_config_files = {"app.json", "metro.config.js", "babel.config.js", "eas.json"}
        has_mobile_configs = bool(mobile_config_files & file_set)

        # 2. React Native imports in package.json
        pkg_content = (
            self.read_file(project_id, "package.json")
            or self.read_file(project_id, "frontend/package.json")
            or ""
        )
        has_react_native_dep = "react-native" in pkg_content or '"expo"' in pkg_content

        # 3. No backend/ directory and no requirements.txt → client-only → likely mobile
        has_backend_dir = any(f.startswith("backend/") for f in files)
        has_requirements = any("requirements" in f for f in files)

        is_mobile = has_mobile_configs or has_react_native_dep or (
            has_react_native_dep and not has_backend_dir
        )

        stack = {
            "backend_language": "none" if is_mobile else "python",
            "is_mobile": is_mobile,
            "has_expo": has_mobile_configs or ('"expo"' in pkg_content),
            "has_fastapi": any("fastapi" in f or "main.py" in f for f in files),
            "has_react": any("package.json" in f or ".tsx" in f for f in files),
            "has_typescript": any(".ts" in f or ".tsx" in f for f in files),
            "has_requirements": has_requirements,
            "has_package_json": "package.json" in file_set or "frontend/package.json" in file_set,
            "backend_entry": self._find_entry_point(project_id),
            "backend_port": 8000,
            "frontend_port": 3000,
        }

        reqs = self.get_requirements_txt(project_id) or ""
        stack["uses_sqlalchemy"] = "sqlalchemy" in reqs.lower()
        stack["uses_alembic"] = "alembic" in reqs.lower()
        stack["uses_redis"] = "redis" in reqs.lower()
        stack["uses_celery"] = "celery" in reqs.lower()

        # ── Project type detection from file heuristics ──────────────────────
        # Priority: most-specific signals checked first.
        ml_files = {"train.py", "evaluate.py", "predict.py"}
        has_ml_files = bool(ml_files & file_set)
        has_ml_reqs = any(kw in pkg_content for kw in ("torch", "tensorflow", "keras", "sklearn", "jax"))
        has_ml_reqs = has_ml_reqs or any(kw in (self.get_requirements_txt(project_id) or "") for kw in ("torch", "tensorflow", "keras", "sklearn"))

        has_airflow = any("airflow" in f or "dag" in f for f in files)
        has_prefect = any("flow" in f and ".py" in f for f in files)
        has_cli = any(f in file_set for f in {"cli/main.py", "main.go", "cmd/main.go"}) or any("typer" in pkg_content or "click" in pkg_content for _ in ["once"])

        if is_mobile:
            project_type = "mobile_app"
        elif has_ml_files or has_ml_reqs:
            project_type = "ml_pipeline"
        elif has_airflow or has_prefect:
            project_type = "data_pipeline"
        elif has_cli:
            project_type = "cli_tool"
        elif not has_backend_dir and not has_requirements:
            # SPA / static site
            project_type = "web_frontend"
        else:
            project_type = "web_fullstack"

        stack["project_type"] = project_type

        logger.info(
            "Tech stack for %s: project_type=%s is_mobile=%s has_expo=%s has_fastapi=%s",
            project_id, project_type, is_mobile, stack["has_expo"], stack["has_fastapi"],
        )
        return stack

    def _find_entry_point(self, project_id: str) -> str:
        """Find the main backend entry point."""
        for candidate in ["backend/main.py", "backend/app/main.py", "main.py", "app.py"]:
            if self.read_file(project_id, candidate):
                return candidate
        return "backend/main.py"
