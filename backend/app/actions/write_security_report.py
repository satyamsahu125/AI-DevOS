from __future__ import annotations

from ..prompt.security_builder import SecurityPromptBuilder
from ..shared.schemas.security_report_schema import SecurityReport
from .base_action import LLMAction


class WriteSecurityReportAction(LLMAction):
    """Security's action: produces a structured SecurityReport."""

    name = "WriteSecurityReport"
    description = "Audit the implementation for OWASP Top 10 / STRIDE findings."
    schema_model = SecurityReport
    system_prompt = (
        "You are a Chief Security Officer running an OWASP Top 10 + STRIDE audit. "
        "Respond with ONLY a single JSON object (no prose outside it) with these keys: "
        "scope (string), findings (list of objects with id/severity/confidence/category/title/"
        "file/line/description/exploit_scenario/recommendation), totals (object mapping severity to count), "
        "remediation_plan (list of strings)."
    )

    def __init__(self, prompt_builder: SecurityPromptBuilder | None = None) -> None:
        """Wire the Security prompt builder this action uses."""
        super().__init__(prompt_builder or SecurityPromptBuilder())
