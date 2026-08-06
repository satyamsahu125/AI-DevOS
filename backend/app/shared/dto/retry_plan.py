from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetryPlan:
    """Decision produced by IntelligentRetryEngine after each rejected stage output.

    Replaces the simple bool from RetryPolicy.should_retry() with a structured
    decision that carries a strategy, a targeted prompt instruction, and the
    reasoning so the retry attempt does something different instead of repeating
    the same request verbatim.

    Consumers (WorkflowEngine) check `should_retry` first; if True, they inject
    `prompt_instruction` into the next attempt's prompt and log `reason` for
    observability.
    """

    should_retry: bool
    strategy: str = "auto_fix"        # "auto_fix" | "full_rewrite" | "escalate" | "stop"
    prompt_instruction: str = ""      # injected into the retry prompt
    reason: str = ""                  # why this decision was made (for logs / observability)
    delay_ms: int = 0                 # future: introduce back-off between retries
    attempt: int = 0                  # the attempt number that produced this plan
    stage: str = ""                   # stage name for context
    rejection_type: str = ""          # "auto_fix" | "ask_human" | "flag" | "unknown"

    @property
    def should_stop(self) -> bool:
        return not self.should_retry
