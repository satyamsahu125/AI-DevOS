from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetryPlan:
    """Decision produced by IntelligentRetryEngine after each rejected stage output.

    Replaces the simple bool from RetryPolicy.should_retry() with a structured
    decision that carries a strategy, a targeted prompt instruction, LLM config
    overrides, and the reasoning so the retry attempt does something different
    instead of repeating the same request verbatim.

    Consumers (StageRunner) check `should_retry` first; if True, they inject
    `prompt_instruction` into the next attempt's prompt, apply `modified_config`
    overrides to the LLM call, and log `reason` for observability.
    """

    should_retry: bool
    strategy: str = "auto_fix"        # "auto_fix" | "full_rewrite" | "escalate" | "stop"
    prompt_instruction: str = ""      # injected into the retry prompt
    reason: str = ""                  # why this decision was made (for logs / observability)
    delay_ms: int = 0                 # future: introduce back-off between retries
    attempt: int = 0                  # the attempt number that produced this plan
    stage: str = ""                   # stage name for context
    rejection_type: str = ""          # "auto_fix" | "ask_human" | "flag" | "unknown"
    modified_config: dict = field(default_factory=dict)
    # LLM config overrides for the next attempt, e.g.:
    #   {"max_tokens": 16384}          — field_reminder, token_rebalance strategies
    #   {"temperature": 0.05}          — schema_injection strategy
    # StageRunner logs these; end-to-end application requires execute_stage to
    # accept config kwargs (future task).

    @property
    def should_stop(self) -> bool:
        return not self.should_retry
