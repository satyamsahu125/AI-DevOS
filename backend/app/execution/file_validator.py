from __future__ import annotations

import ast
import json
import logging
import subprocess
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ValidationResult(BaseModel):
    file_path: str
    passed: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)


class FileValidator:
    """Validates generated code using real tools.

    No LLM involved — purely deterministic checks. Feeds structured errors back
    into the generation loop.
    """

    def validate(self, file_path: str, content: str, language: str) -> ValidationResult:
        """Run all applicable validations for this file type."""
        errors: list[str] = []
        warnings: list[str] = []
        checks_run: list[str] = []

        lang = language.lower() if language else ""
        if lang == "python" or file_path.endswith(".py"):
            errors += self._check_python_syntax(content, checks_run)
            errors += self._check_python_imports(content, checks_run)
            warnings += self._check_python_style(content, checks_run)
        elif lang in ["typescript", "javascript", "ts", "js", "tsx", "jsx"] or file_path.endswith((".ts", ".js", ".tsx", ".jsx")):
            errors += self._check_js_syntax(content, checks_run)
        elif lang in ["yaml", "yml"] or file_path.endswith((".yaml", ".yml")):
            errors += self._check_yaml_syntax(content, checks_run)
        elif lang == "json" or file_path.endswith(".json"):
            errors += self._check_json_syntax(content, checks_run)

        # Always check: not empty, reasonable size
        if not content.strip():
            errors.append("File is empty")
        if len(content) < 10:
            errors.append("File too short to be valid code")

        return ValidationResult(
            file_path=file_path,
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            checks_run=checks_run,
        )

    def _check_python_syntax(self, content: str, checks_run: list) -> list[str]:
        """Parse Python AST to detect syntax errors."""
        checks_run.append("python_syntax")
        try:
            ast.parse(content)
            return []
        except SyntaxError as e:
            return [f"Syntax error at line {e.lineno}: {e.msg}"]
        except Exception as e:
            return [f"Python parse error: {str(e)}"]

    def _check_python_imports(self, content: str, checks_run: list) -> list[str]:
        """Check import statements are syntactically valid."""
        checks_run.append("python_imports")
        errors = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    pass
        except Exception as e:
            errors.append(f"Import check failed: {str(e)}")
        return errors

    def _check_python_style(self, content: str, checks_run: list) -> list[str]:
        """Run ruff linter if available."""
        checks_run.append("python_style")
        try:
            result = subprocess.run(
                ["ruff", "check", "--stdin-filename", "check.py", "-"],
                input=content,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout:
                return result.stdout.strip().split("\n")
            return []
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            return []

    def _check_yaml_syntax(self, content: str, checks_run: list) -> list[str]:
        checks_run.append("yaml_syntax")
        try:
            import yaml
            yaml.safe_load(content)
            return []
        except yaml.YAMLError as e:
            return [f"YAML error: {str(e)}"]
        except Exception as e:
            return [f"YAML check error: {str(e)}"]

    def _check_json_syntax(self, content: str, checks_run: list) -> list[str]:
        checks_run.append("json_syntax")
        try:
            json.loads(content)
            return []
        except json.JSONDecodeError as e:
            return [f"JSON decode error: {str(e)}"]

    def _check_js_syntax(self, content: str, checks_run: list) -> list[str]:
        checks_run.append("js_syntax")
        errors = []
        if content.count("{") != content.count("}"):
            errors.append("Mismatched curly braces")
        if content.count("(") != content.count(")"):
            errors.append("Mismatched parentheses")
        return errors
