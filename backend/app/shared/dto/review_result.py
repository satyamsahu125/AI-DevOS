from dataclasses import dataclass

from ..models.review import Review


@dataclass(slots=True)
class ReviewResult:
    review: Review
    approved: bool
