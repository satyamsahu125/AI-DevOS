from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ReviewResult:
    approved: bool
    score: float
    feedback: str
    retry_required: bool
    reviewer: str
