from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RecoveryPolicy:
    """Policy used by the execution recovery runtime."""

    allow_rollback: bool = True
    max_retries: int = 3
