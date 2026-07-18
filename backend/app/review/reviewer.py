from __future__ import annotations

from ..shared.models.stage_artifact import StageArtifact
from ..shared.dto.review_result import ReviewResult
from ..shared.enums.review_decision import ReviewDecision
from ..shared.models.review import Review


class Reviewer:
    """Documented review entrypoint used by the runtime."""

    def review(self, artifact: StageArtifact) -> ReviewResult:
        approved = bool(artifact.content and artifact.content.strip())
        review = Review(
            review_id="",
            artifact_id=artifact.artifact_id,
            decision=ReviewDecision.Approved if approved else ReviewDecision.Rejected,
            feedback="Artifact content is present" if approved else "Artifact content is empty",
        )
        return ReviewResult(review=review, approved=approved)
