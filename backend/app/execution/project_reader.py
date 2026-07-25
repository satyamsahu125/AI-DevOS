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

    def read_all_backend_files(self, project_id: str) -> dict[str, str]:
        """Returns dict of {relative_path: file_content} for all Python files in backend/ directory.

        Truncates files over 2000 chars to save context.
        """
        project_dir = self.get_project_dir(project_id)
        backend_dir = project_dir / "backend"

        if not backend_dir.exists():
            logger.warning("No backend directory found for %s", project_id)
            return {}

        files = {}
        for path in sorted(backend_dir.rglob("*.py")):
            rel_path = str(path.relative_to(project_dir)).replace("\\", "/")
            try:
                content = path.read_text(encoding="utf-8")
                if len(content) > 2000:
                    content = content[:2000] + "\n# ... [truncated]"
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

    def list_all_files(self, project_id: str) -> list[str]:
        """List all files in project directory."""
        project_dir = self.get_project_dir(project_id)
        if not project_dir.exists():
            return []
        return [
            str(p.relative_to(project_dir)).replace("\\", "/")
            for p in sorted(project_dir.rglob("*"))
            if p.is_file() and ".attempt-" not in p.name and "_attempt_" not in p.name
        ]

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
        """Parse model files to extract SQLAlchemy models.

        Returns list of {class_name, file} Used by QA and DevOps to understand data
        structure.
        """
        models = []
        backend_files = self.read_all_backend_files(project_id)

        for file_path, content in backend_files.items():
            if "model" not in file_path:
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

        Used by DevOps to write correct Dockerfile.
        """
        files = self.list_all_files(project_id)
        file_set = set(files)

        stack = {
            "backend_language": "python",
            "has_fastapi": any("fastapi" in f or "main.py" in f for f in files),
            "has_react": any("package.json" in f or ".tsx" in f for f in files),
            "has_typescript": any(".ts" in f or ".tsx" in f for f in files),
            "has_requirements": any("requirements" in f for f in files),
            "has_package_json": "frontend/package.json" in file_set,
            "backend_entry": self._find_entry_point(project_id),
            "backend_port": 8000,
            "frontend_port": 3000,
        }

        reqs = self.get_requirements_txt(project_id) or ""
        stack["uses_sqlalchemy"] = "sqlalchemy" in reqs.lower()
        stack["uses_alembic"] = "alembic" in reqs.lower()
        stack["uses_redis"] = "redis" in reqs.lower()
        stack["uses_celery"] = "celery" in reqs.lower()

        return stack

    def _find_entry_point(self, project_id: str) -> str:
        """Find the main backend entry point."""
        for candidate in ["backend/main.py", "backend/app/main.py", "main.py", "app.py"]:
            if self.read_file(project_id, candidate):
                return candidate
        return "backend/main.py"
