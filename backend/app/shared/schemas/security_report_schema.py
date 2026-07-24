from __future__ import annotations

from typing import Union

from pydantic import BaseModel, Field


class SecurityFinding(BaseModel):
    """One security finding (inspired by gstack's /cso OWASP Top 10 + STRIDE audit).

    confidence/line accept either a number or a string: this stage runs before
    BackendDeveloper/FrontendDeveloper in the pipeline (see DependencyGraph),
    so there is no real source file yet to give an exact line number -- models
    correctly answer "N/A" -- and confidence is naturally categorical
    ("High"/"Medium"/"Low"), matching how severity is already typed.
    """

    id: str = ""
    severity: str = ""
    confidence: Union[int, str] = ""
    category: str = ""
    title: str = ""
    file: str = ""
    line: Union[int, str] = ""
    description: str = ""
    exploit_scenario: str = ""
    recommendation: str = ""


class SecurityReport(BaseModel):
    """Structured output of the Security stage (inspired by gstack's /cso skill)."""

    scope: str = ""
    findings: list[SecurityFinding] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=dict)
    remediation_plan: list[str] = Field(default_factory=list)
