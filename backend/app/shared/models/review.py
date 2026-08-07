from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..enums.review_decision import ReviewDecision


@dataclass
class Review:
    review_id: str
    artifact_id: str
    decision: ReviewDecision = ReviewDecision.Approved
    feedback: str = ""
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
