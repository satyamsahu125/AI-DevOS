import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory.knowledge_memory import KnowledgeMemory
from app.memory.learning_loop import LearningLoop
from app.review.reviewer import ReviewFinding, ReviewResult, ReviewTier, Reviewer
from app.shared.models.stage_artifact import StageArtifact


class ReviewerUpgradeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="reviewer_test_"))
        knowledge_memory = KnowledgeMemory(
            db_path=self._tmp_dir / "knowledge.db",
            index_path=self._tmp_dir / "knowledge.hnsw",
            max_elements=20,
        )
        learning_loop = LearningLoop(knowledge_memory=knowledge_memory, db_path=self._tmp_dir / "learning.db")
        self.reviewer = Reviewer(learning_loop=learning_loop)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _artifact(self, **overrides) -> StageArtifact:
        defaults = dict(artifact_id="a1", name="product-owner-output", content="A perfectly fine requirements document.")
        defaults.update(overrides)
        return StageArtifact(**defaults)

    def test_empty_content_triggers_auto_fix_not_approval(self) -> None:
        result = self.reviewer.review(self._artifact(content=""))

        self.assertIsInstance(result, ReviewResult)
        self.assertFalse(result.approved)
        self.assertTrue(any(f.tier == ReviewTier.AUTO_FIX for f in result.findings))
        self.assertTrue(result.auto_fixes_applied)

    def test_missing_schema_fields_triggers_ask_human(self) -> None:
        artifact = self._artifact(
            content="Some content was produced but not as structured JSON.",
            schema_type="WriteRequirements",
            structured_content={},
        )

        result = self.reviewer.review(artifact)

        self.assertFalse(result.approved)
        self.assertTrue(any(f.tier == ReviewTier.ASK_HUMAN for f in result.findings))
        self.assertTrue(result.human_questions)

    def test_quality_score_below_threshold_triggers_flag(self) -> None:
        # Long enough to avoid the ASK_HUMAN "too short" trigger, short enough to lower quality_score.
        artifact = self._artifact(content="Short but present output")

        result = self.reviewer.review(artifact)

        self.assertTrue(any(f.tier == ReviewTier.FLAG for f in result.findings))
        self.assertLess(result.quality_score, 0.6)
        self.assertFalse(result.human_questions)

    def test_clean_artifact_is_approved_with_no_findings(self) -> None:
        artifact = self._artifact(content="A" * 200)

        result = self.reviewer.review(artifact)

        self.assertTrue(result.approved)
        self.assertEqual(result.findings, [])
        self.assertEqual(result.quality_score, 1.0)

    def test_structured_content_present_does_not_trigger_ask_human(self) -> None:
        artifact = self._artifact(
            content="A" * 200,
            schema_type="WriteRequirements",
            structured_content={"project_name": "Demo"},
        )

        result = self.reviewer.review(artifact)

        self.assertTrue(result.approved)
        self.assertFalse(any(f.tier == ReviewTier.ASK_HUMAN for f in result.findings))

    def test_repeated_content_from_previous_attempt_triggers_flag(self) -> None:
        artifact = self._artifact(content="A" * 200)

        result = self.reviewer.review(artifact, previous_content="A" * 200)

        self.assertTrue(any("identical to the previous attempt" in flag for flag in result.flags))

    def test_review_finding_and_result_are_pydantic_models(self) -> None:
        finding = ReviewFinding(tier=ReviewTier.FLAG, description="test", suggestion="test")
        self.assertEqual(finding.tier, ReviewTier.FLAG)


if __name__ == "__main__":
    unittest.main()
