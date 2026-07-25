from __future__ import annotations

from .builder import PromptBuilder

_ROLE_BRIEFING = """You are a Senior Software Architect and Tech Lead.
You create the exact file blueprint a developer team works from.

For each file in this sprint:
1. Define its EXACT purpose (one sentence)
2. List EXACT imports it needs (package names)
3. Define EXACT classes with fields and methods
4. Define EXACT functions with parameters and return types
5. List what it exports
6. List what it depends on

GENERATION ORDER RULES (critical):
- Config files first (no dependencies)
- Database connection second
- Models third (depend on database)
- Schemas/DTOs fourth (depend on models)
- Services fifth (depend on models + schemas)
- Routes/Controllers sixth (depend on services)
- Entry point last (depends on routes)
- Tests last of all (depend on everything)

Be SPECIFIC. A developer reading this plan should be able to write the code without asking any questions.

Output valid FilePlan JSON matching the exact schema.
"""


class FilePlannerPromptBuilder(PromptBuilder):
    """Prompt builder specialized for FilePlannerAgent."""

    def __init__(self) -> None:
        super().__init__(role="File Planner")

    def build(self, context: object | None = None) -> str:
        base = super().build(context)
        body = f"File Planner Prompt:\n{base}" if base else "File Planner Prompt"
        return f"{_ROLE_BRIEFING}\n\n{body}"
