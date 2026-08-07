from __future__ import annotations

from .result import ReviewResult


class ReviewValidator:
    """Validate review output shape and content."""

    def validate(self, result: ReviewResult) -> bool:
        return isinstance(result, ReviewResult) and isinstance(result.score, (int, float))
