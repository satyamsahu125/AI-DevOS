from __future__ import annotations

from dataclasses import dataclass

from .recovery_checkpoint import RecoveryCheckpoint


@dataclass(slots=True)
class RecoveryResult:
    success: bool
    checkpoint: RecoveryCheckpoint | None = None
    message: str = ""
