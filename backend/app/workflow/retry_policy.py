from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class RetryPolicy:
    """Retry policy consulted by WorkflowEngine after every rejected stage review.

    Attempts are zero-indexed: should_retry(0) governs whether the first
    execution attempt is allowed, should_retry(1) the first retry, and so on.
    """

    def __init__(self, max_retries: int = 3) -> None:
        """Initialize the policy with the maximum number of attempts allowed for a stage."""
        self.max_retries = max_retries

    def should_retry(self, attempt: int) -> bool:
        """Return True if another execution attempt is permitted for the given attempt index."""
        allowed = attempt < self.max_retries
        logger.debug("retry policy check: attempt=%s max_retries=%s allowed=%s", attempt, self.max_retries, allowed)
        return allowed
