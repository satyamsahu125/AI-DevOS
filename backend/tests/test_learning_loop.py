import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.memory.knowledge_memory import KnowledgeMemory
from app.memory.learning_loop import AgentPerformance, LearningLoop, Trajectory


class LearningLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="learning_loop_test_"))
        self.km = KnowledgeMemory(
            db_path=self._tmp_dir / "knowledge.db",
            index_path=self._tmp_dir / "knowledge.hnsw",
            max_elements=20,
        )
        self.loop = LearningLoop(knowledge_memory=self.km, db_path=self._tmp_dir / "learning.db")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _trajectory(self, **overrides) -> Trajectory:
        defaults = dict(
            stage="WriteRequirements",
            task_description="build a todo API",
            artifact_summary="Requirements for a todo API with FastAPI: goals, user stories, acceptance criteria.",
            retry_count=0,
            approved=True,
            reviewer_feedback="",
            agent_model="qwen2.5-coder:7b",
            tokens_used=300,
            latency_ms=1200.0,
        )
        defaults.update(overrides)
        return Trajectory(**defaults)

    def test_approved_trajectory_is_in_semantic_search(self) -> None:
        self.loop.record_trajectory(self._trajectory(approved=True))

        patterns = self.loop.get_relevant_patterns("build a todo list API", "WriteRequirements")

        self.assertTrue(any("todo API" in p for p in patterns))

    def test_rejected_trajectory_not_in_semantic_search(self) -> None:
        self.loop.record_trajectory(
            self._trajectory(
                approved=False,
                task_description="build a chat application",
                artifact_summary="incomplete output missing acceptance criteria",
                reviewer_feedback="missing acceptance criteria",
                retry_count=1,
            )
        )

        patterns = self.loop.get_relevant_patterns("build a chat application", "WriteRequirements")

        self.assertEqual(patterns, [])

    def test_get_relevant_patterns_only_searches_matching_stage(self) -> None:
        self.loop.record_trajectory(self._trajectory(stage="WriteArchitecture", approved=True))

        patterns = self.loop.get_relevant_patterns("build a todo API", "WriteRequirements")

        self.assertEqual(patterns, [])

    def test_get_agent_performance_returns_correct_stats(self) -> None:
        self.loop.record_trajectory(self._trajectory(approved=True, retry_count=0, tokens_used=300, latency_ms=1000.0))
        self.loop.record_trajectory(
            self._trajectory(approved=False, retry_count=1, tokens_used=150, latency_ms=800.0, reviewer_feedback="bad")
        )

        performance = self.loop.get_agent_performance("WriteRequirements")

        self.assertIsInstance(performance, AgentPerformance)
        self.assertEqual(performance.total, 2)
        self.assertEqual(performance.success_rate, 0.5)
        self.assertEqual(performance.avg_retries, 0.5)
        self.assertEqual(performance.avg_tokens, 225.0)
        self.assertEqual(performance.avg_latency, 900.0)

    def test_get_agent_performance_for_unknown_stage_is_zeroed(self) -> None:
        performance = self.loop.get_agent_performance("NeverRan")

        self.assertEqual(performance, AgentPerformance())

    def test_get_failure_patterns_returns_rejected_feedback_only(self) -> None:
        self.loop.record_trajectory(self._trajectory(approved=True))
        self.loop.record_trajectory(
            self._trajectory(approved=False, reviewer_feedback="missing acceptance criteria", retry_count=1)
        )

        failures = self.loop.get_failure_patterns("WriteRequirements")

        self.assertEqual(failures, ["missing acceptance criteria"])


if __name__ == "__main__":
    unittest.main()
