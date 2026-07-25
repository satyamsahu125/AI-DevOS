from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class QuestionOption(BaseModel):
    value: str
    label: str


class Question(BaseModel):
    index: int
    question: str
    category: str = "WHAT_IS_IT"
    priority: str = "MAJOR"
    options: list[QuestionOption] | None = None
    allows_custom: bool = True
    skippable: bool = False


class QASession(BaseModel):
    status: str = "pending"
    total_questions: int = 0
    answered: int = 0
    questions: list[Question] = Field(default_factory=list)
    answers: list[dict[str, Any]] = Field(default_factory=list)
    completed: bool = False


class QuestionSet(BaseModel):
    """Output of Phase A — just the questions."""
    questions: list[Question] = Field(default_factory=list)
