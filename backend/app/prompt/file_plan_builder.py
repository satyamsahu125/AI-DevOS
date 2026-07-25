from __future__ import annotations

from .builder import PromptBuilder

_ROLE_BRIEFING = """You are a Senior Staff Systems Planner mapping architecture into clean, executable source file trees.

Core Rules & Path Integrity:
- Relative Clean Paths Only: Every planned path MUST be relative to its target directory (e.g., 'src/components/Calculator.jsx', 'app/main.py', 'routes/auth.js').
- ZERO Doubled Directory Prefixes: NEVER write 'frontend/frontend/...' or 'backend/backend/...'.
- NO URL-Style Paths: Never use route paths like '/api/users' or '/search' as file paths. Translate API routes to source files like 'routes/users.js' or 'controllers/search_controller.py'.
- Responsible Stage Assignment: Explicitly assign every file responsible_stage as either 'backend' or 'frontend'.
"""


class FilePlanPromptBuilder(PromptBuilder):
    """Advanced prompt builder for File Structure Planner stage."""

    def __init__(self) -> None:
        super().__init__(role="File Structure Planner")

    def build(self, context: object | None = None) -> str:
        base = super().build(context)
        body = f"File Plan Prompt:\n{base}" if base else "File Plan Prompt"
        return f"{_ROLE_BRIEFING}\n\n{body}"
