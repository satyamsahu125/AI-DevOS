from __future__ import annotations

import logging
from typing import Any

from ..shared.dto.retry_plan import RetryPlan

logger = logging.getLogger(__name__)

# Reviewer tier strings (must match Reviewer implementation)
_TIER_FLAG = "flag"
_TIER_ASK_HUMAN = "ask_human"
_TIER_AUTO_FIX = "auto_fix"


class IntelligentRetryEngine:
    """Rejection-type-aware retry decision engine.

    Replaces RetryPolicy's blind `attempt < max_retries` with a structured
    decision that:
      1. Classifies the rejection by tier (auto_fix / ask_human / flag).
      2. Adjusts max_retries based on historical agent performance (if scorer
         is wired in) — high-performing agents get fewer retries; chronic
         failures get stopped earlier to save tokens.
      3. Produces a targeted prompt_instruction specific to the rejection type
         so the agent knows what to actually fix on the next attempt.

    Falls back to `max_retries` behavior when no scorer or review_result is
    available, preserving full backward compatibility.
    """

    def __init__(
        self,
        max_retries: int = 3,
        performance_scorer: Any | None = None,
    ) -> None:
        self.max_retries = max_retries
        self.performance_scorer = performance_scorer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan(
        self,
        attempt: int,
        review_result: Any | None = None,
        stage: str = "",
        project_id: str = "",
    ) -> RetryPlan:
        """Produce a RetryPlan after a rejection.

        Args:
            attempt:       Current 0-indexed attempt number (same as RetryPolicy).
            review_result: Reviewer output — read .findings and .overall_feedback.
            stage:         Stage name for performance lookup and logging.
            project_id:    Project ID for logging.

        Returns:
            RetryPlan with should_retry, strategy, prompt_instruction, reason.
        """
        rejection_type = self._classify_rejection(review_result)
        effective_max = self._effective_max_retries(stage, project_id)

        logger.debug(
            "retry_engine.plan: stage=%s attempt=%s rejection_type=%s effective_max=%s",
            stage, attempt, rejection_type, effective_max,
        )

        # FLAG → stop immediately — reviewer says this is unsafe/unresolvable
        if rejection_type == _TIER_FLAG:
            return RetryPlan(
                should_retry=False,
                strategy="stop",
                reason=f"Reviewer flagged output as unresolvable at attempt {attempt}",
                rejection_type=rejection_type,
                attempt=attempt,
                stage=stage,
            )

        # Retry budget exhausted
        if attempt >= effective_max:
            return RetryPlan(
                should_retry=False,
                strategy="stop",
                reason=f"Exhausted retry budget (attempt {attempt} >= effective_max {effective_max})",
                rejection_type=rejection_type,
                attempt=attempt,
                stage=stage,
            )

        # ASK_HUMAN on a later attempt → escalate (don't waste more tokens)
        if rejection_type == _TIER_ASK_HUMAN and attempt >= 1:
            return RetryPlan(
                should_retry=False,
                strategy="escalate",
                reason="Reviewer requires human input; escalating rather than retrying",
                prompt_instruction=(
                    "The reviewer indicates human judgement is required to resolve this. "
                    "Provide the clearest possible output so a human can review it."
                ),
                rejection_type=rejection_type,
                attempt=attempt,
                stage=stage,
            )

        # First attempt ASK_HUMAN or any AUTO_FIX → retry with targeted instruction
        strategy = "auto_fix" if rejection_type == _TIER_AUTO_FIX else "full_rewrite"
        instruction = self._build_instruction(rejection_type, review_result, attempt)

        return RetryPlan(
            should_retry=True,
            strategy=strategy,
            prompt_instruction=instruction,
            reason=f"Rejection type={rejection_type}; attempt {attempt} < {effective_max}; retrying",
            rejection_type=rejection_type,
            attempt=attempt,
            stage=stage,
        )

    def should_retry(self, attempt: int) -> bool:
        """Backward-compatible interface matching RetryPolicy.should_retry().

        Use plan() for the full decision with rejection-type awareness.
        This method only checks the attempt budget, not the rejection type.
        """
        return attempt < self.max_retries

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify_rejection(self, review_result: Any | None) -> str:
        """Return the dominant rejection tier from review_result.findings.

        Priority: flag > ask_human > auto_fix > unknown.
        """
        if review_result is None:
            return "unknown"
        findings = getattr(review_result, "findings", None) or []
        if not findings:
            return "unknown"
        tiers = set()
        for f in findings:
            tier = getattr(f, "tier", None)
            if tier is not None:
                tier_val = tier.value if hasattr(tier, "value") else str(tier).lower()
                tiers.add(tier_val)
        if _TIER_FLAG in tiers:
            return _TIER_FLAG
        if _TIER_ASK_HUMAN in tiers:
            return _TIER_ASK_HUMAN
        if _TIER_AUTO_FIX in tiers:
            return _TIER_AUTO_FIX
        return "unknown"

    def _effective_max_retries(self, stage: str, project_id: str) -> int:
        """Adjust max_retries based on historical performance score.

        High performers (score >= 0.85) get 1 extra attempt (they're unlikely to
        need it but we give them room). Chronic failures (score < 0.50, avg_retries
        > 2) are capped at 2 to avoid wasting tokens on a broken prompt.
        Returns self.max_retries if scorer unavailable or stage has no history.
        """
        if self.performance_scorer is None:
            return self.max_retries
        try:
            perf = self.performance_scorer.score_agent(stage, project_id)
            score = perf.get("score")
            avg_retries = perf.get("avg_retries", 0.0)
            if score is None:
                return self.max_retries
            if score >= 0.85:
                return min(self.max_retries + 1, 5)
            if score < 0.50 and avg_retries > 2:
                return max(2, self.max_retries - 1)
        except Exception as exc:
            logger.debug("_effective_max_retries: scorer failed for %s: %s", stage, exc)
        return self.max_retries

    def _build_instruction(self, rejection_type: str, review_result: Any | None, attempt: int) -> str:
        """Build a targeted prompt instruction for the next retry attempt."""
        base = ""
        if review_result is not None:
            findings = getattr(review_result, "findings", None) or []
            auto_fix_suggestions = [
                getattr(f, "suggestion", "") for f in findings
                if (getattr(getattr(f, "tier", None), "value", str(getattr(f, "tier", ""))) or "").lower() == _TIER_AUTO_FIX
                and getattr(f, "suggestion", "")
            ]
            if auto_fix_suggestions:
                base = " Apply these specific fixes: " + "; ".join(auto_fix_suggestions[:3]) + "."

        if rejection_type == _TIER_AUTO_FIX:
            return (
                f"[Retry {attempt + 1}] The previous output had structural or schema issues. "
                f"Ensure your response matches the expected JSON schema exactly.{base}"
            )
        if rejection_type == _TIER_ASK_HUMAN:
            return (
                f"[Retry {attempt + 1}] The reviewer needs clearer output to provide feedback. "
                "Be more specific and complete in your response — include all required fields."
            )
        return (
            f"[Retry {attempt + 1}] The previous output was rejected. "
            f"Review all requirements and produce a corrected, complete response.{base}"
        )
