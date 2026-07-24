import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.execution.safety_policy import FreezePolicy, OperationType, SafetyDecision, SafetyPolicy


class SafetyPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="safety_policy_test_"))
        self.workspace = self._tmp_dir / "workspace"
        self.workspace.mkdir()
        self.policy = SafetyPolicy(workspace_root=self.workspace, db_path=self._tmp_dir / "safety.db")

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_block_fires_on_file_delete_outside_allowed_dir(self) -> None:
        outside_file = self._tmp_dir / "outside.txt"
        outside_file.write_text("data")

        result = self.policy.check(OperationType.FILE_DELETE, str(outside_file))

        self.assertEqual(result.decision, SafetyDecision.BLOCK)

    def test_allow_fires_on_overwrite_of_unapproved_attempt(self) -> None:
        existing = self.workspace / "existing.md"
        existing.write_text("hello")

        result = self.policy.check(OperationType.FILE_OVERWRITE, str(existing))

        self.assertEqual(result.decision, SafetyDecision.ALLOW)

    def test_allow_fires_on_retry_attempt_overwrite(self) -> None:
        existing = self.workspace / "existing.md"
        existing.write_text("hello")

        result = self.policy.check(OperationType.FILE_OVERWRITE, str(existing), attempt=2)

        self.assertEqual(result.decision, SafetyDecision.ALLOW)

    def test_warn_fires_on_overwrite_of_approved_artifact(self) -> None:
        existing = self.workspace / "existing.md"
        existing.write_text("hello")
        resolved = str(existing.resolve())
        self.policy._conn.execute(
            "CREATE TABLE IF NOT EXISTS artifacts (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, "
            "stage TEXT NOT NULL, file_path TEXT NOT NULL, json_path TEXT NOT NULL, created_at TEXT NOT NULL, "
            "attempt INTEGER NOT NULL, approved INTEGER NOT NULL DEFAULT 0)"
        )
        self.policy._conn.execute(
            "INSERT INTO artifacts (project_id, stage, file_path, json_path, created_at, attempt, approved) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            ("proj-1", "ProductOwner", resolved, resolved, "2026-01-01T00:00:00", 1),
        )
        self.policy._conn.commit()

        result = self.policy.check(OperationType.FILE_OVERWRITE, str(existing))

        self.assertEqual(result.decision, SafetyDecision.WARN)

    def test_allow_fires_on_normal_write_operations(self) -> None:
        new_file = self.workspace / "new.md"

        result = self.policy.check(OperationType.FILE_OVERWRITE, str(new_file))

        self.assertEqual(result.decision, SafetyDecision.ALLOW)

    def test_new_file_write_outside_workspace_is_blocked(self) -> None:
        """A brand-new (nonexistent) path outside workspace_root used to be unconditionally
        ALLOWed -- the existence check short-circuited before the workspace-boundary check ever
        ran, so a leading-slash path escaping the intended project dir would silently "succeed"
        outside it instead of being caught (see project_files.py's _sanitize_relative_path fix,
        which addresses the same underlying bug from the other side)."""
        outside_new_file = self._tmp_dir.parent / "definitely-outside-new-file.txt"
        self.assertFalse(outside_new_file.exists())

        result = self.policy.check(OperationType.FILE_OVERWRITE, str(outside_new_file))

        self.assertEqual(result.decision, SafetyDecision.BLOCK)

    def test_destructive_op_inside_workspace_warns_not_blocks(self) -> None:
        target = self.workspace / "temp.txt"
        target.write_text("data")

        result = self.policy.check(OperationType.FILE_DELETE, str(target))

        self.assertEqual(result.decision, SafetyDecision.WARN)

    def test_every_check_is_logged_to_observability_memory(self) -> None:
        self.policy.check(OperationType.FILE_OVERWRITE, str(self.workspace / "a.md"))
        self.policy.check(OperationType.FILE_DELETE, str(self._tmp_dir / "b.txt"))

        rows = self.policy._conn.execute("SELECT COUNT(*) FROM safety_checks").fetchone()
        self.assertEqual(rows[0], 2)

    def test_guarded_operations_lists_every_operation_type(self) -> None:
        self.assertEqual(set(SafetyPolicy.GUARDED_OPERATIONS), set(OperationType))


class FreezePolicyTests(unittest.TestCase):
    def test_is_allowed_true_when_no_freeze_set(self) -> None:
        policy = FreezePolicy()
        self.assertTrue(policy.is_allowed("/anywhere/at/all.txt"))

    def test_set_freeze_blocks_paths_outside_boundary(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="freeze_test_"))
        allowed = tmp_dir / "allowed"
        allowed.mkdir()
        try:
            policy = FreezePolicy()
            policy.set_freeze(str(allowed))

            self.assertTrue(policy.is_allowed(str(allowed / "file.txt")))
            self.assertFalse(policy.is_allowed(str(tmp_dir / "other" / "file.txt")))
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_clear_freeze_restores_full_access(self) -> None:
        policy = FreezePolicy(allowed_dirs=["/some/dir"])
        policy.clear_freeze()
        self.assertTrue(policy.is_allowed("/anywhere/file.txt"))

    def test_freeze_boundary_blocks_even_non_destructive_ops(self) -> None:
        tmp_dir = Path(tempfile.mkdtemp(prefix="freeze_safety_test_"))
        allowed = tmp_dir / "allowed"
        allowed.mkdir()
        try:
            freeze = FreezePolicy()
            freeze.set_freeze(str(allowed))
            policy = SafetyPolicy(workspace_root=tmp_dir, freeze_policy=freeze, db_path=tmp_dir / "safety.db")

            result = policy.check(OperationType.FILE_OVERWRITE, str(tmp_dir / "other.md"))

            self.assertEqual(result.decision, SafetyDecision.BLOCK)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
