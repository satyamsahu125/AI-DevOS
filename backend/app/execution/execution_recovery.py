from __future__ import annotations

from .recovery_checkpoint import RecoveryCheckpoint
from .recovery_policy import RecoveryPolicy
from .recovery_result import RecoveryResult
from .recovery_validation import RecoveryValidation


class ExecutionRecovery:
    """Recovers execution from the latest valid checkpoint."""

    def __init__(self, policy: RecoveryPolicy | None = None, validation: RecoveryValidation | None = None) -> None:
        self.policy = policy or RecoveryPolicy()
        self.validation = validation or RecoveryValidation()

    def create_checkpoint(self, checkpoint: RecoveryCheckpoint) -> RecoveryCheckpoint:
        return checkpoint

    def restore_checkpoint(self, checkpoint: RecoveryCheckpoint) -> RecoveryCheckpoint:
        self.validation.validate(checkpoint)
        return checkpoint

    def resume(self, checkpoint: RecoveryCheckpoint) -> RecoveryResult:
        self.restore_checkpoint(checkpoint)
        return RecoveryResult(success=True, checkpoint=checkpoint, message="resumed")

    def rollback(self, checkpoint: RecoveryCheckpoint) -> RecoveryResult:
        self.restore_checkpoint(checkpoint)
        return RecoveryResult(success=True, checkpoint=checkpoint, message="rolled back")

    def recover(self, checkpoint: RecoveryCheckpoint) -> RecoveryResult:
        return self.resume(checkpoint)

    def validate(self, checkpoint: RecoveryCheckpoint) -> None:
        self.validation.validate(checkpoint)

    def cleanup(self) -> None:
        return None
