from __future__ import annotations

# Import from reviewer.py's ReviewResult (Pydantic model with quality_score)
# NOT from result.py's ReviewResult (dataclass with score) — the two are
# different types and must not be mixed.
from .reviewer import ReviewResult


class ReviewRules:
    """Simple review rules for approval decisions."""

    def is_approved(self, result: ReviewResult) -> bool:
        # Use quality_score, not score — the production ReviewResult (reviewer.py)
        # defines quality_score: float.  result.py's dataclass has score: float
        # but is not used in any production review path.
        return result.approved and result.quality_score >= 0.5
