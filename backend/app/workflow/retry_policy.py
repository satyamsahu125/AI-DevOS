from __future__ import annotations


class RetryPolicy:
    """Minimal retry policy for workflow stages."""

    def __init__(self, max_retries: int = 1) -> None:
        self.max_retries = max_retries

    def should_retry(self, attempt: int) -> bool:
        return attempt < self.max_retries
