from __future__ import annotations

from typing import Union

from pydantic import BaseModel, Field


class TestCase(BaseModel):
    """One test case in a QA report."""

    __test__ = False

    name: str = ""
    steps: list[str] = Field(default_factory=list)
    expected: str = ""
    actual: str = ""
    status: str = ""


class Bug(BaseModel):
    """One bug found during QA.

    line accepts either a number or a string ("N/A") for the same reason as
    SecurityFinding.line: not every bug maps to one exact, known line number.
    """

    id: str = ""
    severity: str = ""
    description: str = ""
    file: str = ""
    line: Union[int, str] = 0


class QAArtifact(BaseModel):
    """Structured output of the QA stage (inspired by MetaGPT's WriteTest/RunCode)."""

    test_cases: list[TestCase] = Field(default_factory=list)
    coverage_percent: float = 0.0
    bugs_found: list[Bug] = Field(default_factory=list)
    regression_tests: list[str] = Field(default_factory=list)
