from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .exceptions import ExecutionException

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "memory" / "memory.db"
_DEFAULT_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]


class OperationType(str, Enum):
    """Kinds of potentially-destructive operations SafetyPolicy guards (inspired by gstack's /careful skill)."""

    FILE_DELETE = "file_delete"
    FILE_OVERWRITE = "file_overwrite"
    DIRECTORY_DELETE = "directory_delete"
    DB_DROP = "db_drop"
    GIT_FORCE_PUSH = "git_force_push"
    GIT_RESET_HARD = "git_reset_hard"


class SafetyDecision(str, Enum):
    """The verdict SafetyPolicy.check() returns for one operation."""

    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"


class SafetyException(ExecutionException):
    """Raised when SafetyPolicy.check() returns BLOCK and the caller proceeds anyway."""


@dataclass(slots=True)
class SafetyCheckResult:
    """The outcome of one SafetyPolicy.check() call."""

    decision: SafetyDecision
    operation: OperationType
    target: str
    reason: str


class FreezePolicy:
    """Restricts writes to a single directory for the session (inspired by gstack's /freeze skill).

    Hard block, not just a warning: when a freeze boundary is set, anything
    outside it is disallowed regardless of operation type. Off by default
    (allowed_dirs empty means nothing is frozen).
    """

    def __init__(self, allowed_dirs: list[str] | None = None) -> None:
        """Wire the initial freeze boundary (empty = no freeze active)."""
        self.allowed_dirs: list[str] = list(allowed_dirs or [])

    def is_allowed(self, file_path: str) -> bool:
        """Return whether file_path is inside the freeze boundary (always True when no freeze is set)."""
        if not self.allowed_dirs:
            return True
        resolved = str(Path(file_path).resolve())
        return any(resolved.startswith(str(Path(directory).resolve())) for directory in self.allowed_dirs)

    def set_freeze(self, directory: str) -> None:
        """Restrict writes to directory only, replacing any previous freeze boundary."""
        logger.info("freeze set: directory=%s", directory)
        self.allowed_dirs = [directory]

    def clear_freeze(self) -> None:
        """Remove the freeze boundary; all directories become allowed again."""
        logger.info("freeze cleared")
        self.allowed_dirs = []


class SafetyPolicy:
    """Warns or blocks destructive operations before they run (inspired by gstack's /careful skill).

    Every check is logged to ObservabilityMemory (the safety_checks SQLite
    table in the same memory.db MemoryManager/CostTracker use) for audit,
    in addition to standard logging.
    """

    GUARDED_OPERATIONS: list[OperationType] = list(OperationType)

    _DESTRUCTIVE = {
        OperationType.FILE_DELETE,
        OperationType.DIRECTORY_DELETE,
        OperationType.DB_DROP,
        OperationType.GIT_FORCE_PUSH,
        OperationType.GIT_RESET_HARD,
    }

    def __init__(
        self,
        workspace_root: Path | None = None,
        freeze_policy: FreezePolicy | None = None,
        db_path: Path | None = None,
    ) -> None:
        """Wire the workspace root (the "safe" zone for destructive ops), FreezePolicy, and audit database."""
        self.workspace_root = Path(workspace_root or _DEFAULT_WORKSPACE_ROOT).resolve()
        self.freeze_policy = freeze_policy or FreezePolicy()
        self._db_path = str(db_path or _DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create the safety_checks audit table on first run."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS safety_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation TEXT NOT NULL,
                target TEXT NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                checked_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def check(self, operation: OperationType, target: str, attempt: int = 1) -> SafetyCheckResult:
        """Check whether operation against target should be allowed, warned about, or blocked.

        attempt is 1-indexed: for FILE_OVERWRITE, any attempt after the first
        is a normal retry writing its own attempt-numbered artifact file
        alongside earlier attempts, not a destructive overwrite, so it is
        always ALLOWed. A first attempt overwriting a file only warrants a
        WARN if that file was a previously *approved* artifact (looked up in
        the same artifacts table ArtifactManager writes to).
        """
        resolved_target = Path(target).resolve()
        in_workspace = self._is_within(resolved_target, self.workspace_root)

        if not self.freeze_policy.is_allowed(str(resolved_target)):
            decision = SafetyDecision.BLOCK
            reason = f"{target} is outside the active freeze boundary"
        elif operation in self._DESTRUCTIVE and not in_workspace:
            decision = SafetyDecision.BLOCK
            reason = f"{operation.value} outside the workspace root is not permitted"
        elif operation in self._DESTRUCTIVE:
            decision = SafetyDecision.WARN
            reason = f"{operation.value} inside the workspace -- proceeding with caution"
        elif operation == OperationType.FILE_OVERWRITE:
            if not resolved_target.exists():
                if in_workspace:
                    decision = SafetyDecision.ALLOW
                    reason = "target does not exist yet -- this is a new write, not an overwrite"
                else:
                    decision = SafetyDecision.BLOCK
                    reason = "new write outside the workspace root is not permitted"
            elif attempt > 1:
                decision = SafetyDecision.ALLOW
                reason = f"writing retry attempt {attempt} alongside previous attempts is expected"
            elif self._is_approved_artifact(str(resolved_target)):
                decision = SafetyDecision.WARN
                reason = "overwriting a previously approved artifact"
            elif in_workspace:
                decision = SafetyDecision.ALLOW
                reason = "overwriting an unapproved artifact attempt inside the workspace"
            else:
                decision = SafetyDecision.BLOCK
                reason = "overwriting an existing file outside the workspace is not permitted"
        else:
            decision = SafetyDecision.ALLOW
            reason = "normal operation"

        result = SafetyCheckResult(decision=decision, operation=operation, target=str(resolved_target), reason=reason)
        self._log_check(result)
        return result

    def _is_approved_artifact(self, target: str) -> bool:
        """Return whether target matches an approved row in the shared artifacts table."""
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                file_path TEXT NOT NULL,
                json_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                approved INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        row = self._conn.execute(
            "SELECT 1 FROM artifacts WHERE file_path = ? AND approved = 1 LIMIT 1", (target,)
        ).fetchone()
        return row is not None

    def _is_within(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _log_check(self, result: SafetyCheckResult) -> None:
        """Log this check to standard logging and persist it to ObservabilityMemory for audit."""
        log_fn = logger.warning if result.decision != SafetyDecision.ALLOW else logger.debug
        log_fn("safety check: operation=%s target=%s decision=%s reason=%s", result.operation.value, result.target, result.decision.value, result.reason)
        self._conn.execute(
            "INSERT INTO safety_checks (operation, target, decision, reason, checked_at) VALUES (?, ?, ?, ?, ?)",
            (result.operation.value, result.target, result.decision.value, result.reason, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
