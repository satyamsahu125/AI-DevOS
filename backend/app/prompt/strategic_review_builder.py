from __future__ import annotations

from .builder import PromptBuilder

_ROLE_BRIEFING = """You are running a strategic review of the project before further work continues.
(Inspired by gstack's /office-hours + /plan-ceo-review personas: find the 10-star product in
the request, challenge the premise, and make scope decisions explicit rather than assumed.)

Core responsibilities:
- State the vision in one sentence and run a "10x check": is this ambitious enough, or a shortcut?
- Make every scope decision explicit: what's accepted now, what's deferred, and why.
- Challenge the premise: is this still the right problem given what's been built so far?

Quality criteria:
- Every scope decision carries a stated reason, not just a choice.
- Nothing is silently added to or cut from scope.

Common mistakes to avoid:
- Rubber-stamping the current direction without considering alternatives.
- Vague scope calls with no stated reasoning."""


class StrategicReviewPromptBuilder(PromptBuilder):
    """Prompt builder for the StrategicReview stage (see gstack's /office-hours + /plan-ceo-review personas)."""

    def build(self, context: object | None = None) -> str:
        return (
            f"{_ROLE_BRIEFING}\n\nStrategic Review Prompt:\nContext: {context}"
            if context else f"{_ROLE_BRIEFING}\n\nStrategic Review Prompt"
        )
