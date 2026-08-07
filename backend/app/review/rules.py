from __future__ import annotations

from .result import ReviewResult


class ReviewRules:
    """Simple review rules for approval decisions."""

    def is_approved(self, result: ReviewResult) -> bool:
        return result.approved and result.score >= 0.5
