from __future__ import annotations


class TokenBudget:
    """Simple token-budget helper for context sizing."""

    def __init__(self, max_tokens: int = 4000) -> None:
        self.max_tokens = max_tokens

    def estimate(self, text: str) -> int:
        return max(1, len(text.split()))

    def within_limit(self, text: str) -> bool:
        return self.estimate(text) <= self.max_tokens
