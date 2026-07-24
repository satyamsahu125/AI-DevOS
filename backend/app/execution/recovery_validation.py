from __future__ import annotations

from .recovery_checkpoint import RecoveryCheckpoint


class RecoveryValidation:
    """Validates checkpoint integrity before recovery."""

    def validate(self, checkpoint: RecoveryCheckpoint) -> None:
        if checkpoint is None:
            raise ValueError("checkpoint is required")
        if not checkpoint.checkpoint_id:
            raise ValueError("checkpoint_id is required")
