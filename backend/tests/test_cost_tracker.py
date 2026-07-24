import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.llm.cost_tracker import CostTracker


class CostTrackerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="cost_tracker_test_"))
        self.tracker = CostTracker(db_path=self._tmp_dir / "cost.db")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_record_creates_schema_on_first_run(self) -> None:
        self.assertTrue((self._tmp_dir / "cost.db").exists())

    def test_get_stage_cost_aggregates_only_that_stage(self) -> None:
        self.tracker.record(stage="WriteRequirements", agent="product_owner", prompt_tokens=10, completion_tokens=5, model="qwen2.5-coder:7b", latency_ms=100.0)
        self.tracker.record(stage="WriteRequirements", agent="product_owner", prompt_tokens=20, completion_tokens=10, model="qwen2.5-coder:7b", latency_ms=200.0)
        self.tracker.record(stage="WriteArchitecture", agent="architect", prompt_tokens=1, completion_tokens=1, model="qwen2.5-coder:7b", latency_ms=1.0)

        summary = self.tracker.get_stage_cost("WriteRequirements")

        self.assertEqual(summary.calls, 2)
        self.assertEqual(summary.prompt_tokens, 30)
        self.assertEqual(summary.completion_tokens, 15)
        self.assertEqual(summary.total_tokens, 45)
        self.assertEqual(summary.total_latency_ms, 300.0)

    def test_get_project_cost_aggregates_only_that_project(self) -> None:
        self.tracker.record(stage="WriteRequirements", agent="product_owner", prompt_tokens=5, completion_tokens=5, model="m", latency_ms=10.0, project_id="proj-a")
        self.tracker.record(stage="WriteRequirements", agent="product_owner", prompt_tokens=100, completion_tokens=100, model="m", latency_ms=10.0, project_id="proj-b")

        summary = self.tracker.get_project_cost("proj-a")

        self.assertEqual(summary.calls, 1)
        self.assertEqual(summary.prompt_tokens, 5)

    def test_get_total_aggregates_everything(self) -> None:
        self.tracker.record(stage="a", agent="x", prompt_tokens=1, completion_tokens=1, model="m", latency_ms=1.0)
        self.tracker.record(stage="b", agent="y", prompt_tokens=2, completion_tokens=2, model="m", latency_ms=2.0)

        summary = self.tracker.get_total()

        self.assertEqual(summary.calls, 2)
        self.assertEqual(summary.total_tokens, 6)

    def test_totals_are_zero_when_nothing_recorded(self) -> None:
        summary = self.tracker.get_total()
        self.assertEqual(summary.calls, 0)
        self.assertEqual(summary.total_tokens, 0)
        self.assertEqual(summary.total_latency_ms, 0.0)

    def test_persists_across_new_tracker_instances_against_same_db(self) -> None:
        self.tracker.record(stage="a", agent="x", prompt_tokens=3, completion_tokens=3, model="m", latency_ms=5.0)

        reopened = CostTracker(db_path=self._tmp_dir / "cost.db")
        summary = reopened.get_total()

        self.assertEqual(summary.calls, 1)
        self.assertEqual(summary.total_tokens, 6)


if __name__ == "__main__":
    unittest.main()
