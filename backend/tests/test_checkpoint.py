import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.session.checkpoint import CheckpointManager, SessionCheckpoint


class CheckpointManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="checkpoint_test_"))
        self.manager = CheckpointManager(db_path=self._tmp_dir / "checkpoints.db")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _checkpoint(self, **overrides) -> SessionCheckpoint:
        defaults = dict(
            session_id="session-1",
            stage="WriteRequirements",
            project_id="proj-a",
            attempt_number=0,
            decisions_made=["used FastAPI"],
            remaining_work=["write tests"],
            failed_approaches=["tried Flask first"],
            last_artifact_summary="Draft requirements for a todo API",
        )
        defaults.update(overrides)
        return SessionCheckpoint(**defaults)

    def test_save_and_restore_round_trip_works(self) -> None:
        checkpoint = self._checkpoint()
        self.manager.save(checkpoint.session_id, checkpoint)

        restored = self.manager.restore(checkpoint.session_id)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.session_id, "session-1")
        self.assertEqual(restored.stage, "WriteRequirements")
        self.assertEqual(restored.project_id, "proj-a")
        self.assertEqual(restored.decisions_made, ["used FastAPI"])
        self.assertEqual(restored.remaining_work, ["write tests"])
        self.assertEqual(restored.failed_approaches, ["tried Flask first"])
        self.assertEqual(restored.last_artifact_summary, "Draft requirements for a todo API")

    def test_restore_returns_none_when_no_checkpoint_exists(self) -> None:
        self.assertIsNone(self.manager.restore("does-not-exist"))

    def test_delete_removes_checkpoint(self) -> None:
        checkpoint = self._checkpoint()
        self.manager.save(checkpoint.session_id, checkpoint)

        self.manager.delete(checkpoint.session_id)

        self.assertIsNone(self.manager.restore(checkpoint.session_id))

    def test_save_overwrites_existing_checkpoint_for_same_session(self) -> None:
        self.manager.save("session-1", self._checkpoint(attempt_number=0))
        self.manager.save("session-1", self._checkpoint(attempt_number=2, decisions_made=["switched approach"]))

        restored = self.manager.restore("session-1")

        self.assertEqual(restored.attempt_number, 2)
        self.assertEqual(restored.decisions_made, ["switched approach"])

    def test_list_incomplete_returns_every_saved_checkpoint(self) -> None:
        self.manager.save("session-1", self._checkpoint(session_id="session-1"))
        self.manager.save("session-2", self._checkpoint(session_id="session-2", stage="WriteArchitecture"))

        incomplete = self.manager.list_incomplete()

        self.assertEqual({c.session_id for c in incomplete}, {"session-1", "session-2"})

    def test_list_incomplete_excludes_deleted_sessions(self) -> None:
        self.manager.save("session-1", self._checkpoint(session_id="session-1"))
        self.manager.save("session-2", self._checkpoint(session_id="session-2"))
        self.manager.delete("session-1")

        incomplete = self.manager.list_incomplete()

        self.assertEqual([c.session_id for c in incomplete], ["session-2"])


if __name__ == "__main__":
    unittest.main()
