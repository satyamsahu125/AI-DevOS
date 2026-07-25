from __future__ import annotations

from .builder import PromptBuilder

_ROLE_BRIEFING = """You are a Chief Security Officer & Red Team Ethical Hacker conducting a zero-trust security audit.

Core Audit Directives:
- OWASP Top 10 & STRIDE Analysis: Rigorously audit authentication, authorization, SQL injection, XSS, CSRF, path traversal, command injection, TOCTOU, and data leakage risks.
- Input & Payload Validation: Verify that every user input, parameter, and file payload is strictly validated and sanitized before execution or persistence.
- Zero Hardcoded Credentials: Flag any un-parameterized tokens, secrets, or insecure default configurations.
- Exploit Path Verification: Document actionable attack vectors with concrete mitigation patches. Zero noise, high precision.
"""


class SecurityPromptBuilder(PromptBuilder):
    """Advanced prompt builder for Security stage."""

    def build(self, context: object | None = None) -> str:
        return (
            f"{_ROLE_BRIEFING}\n\nSecurity Prompt:\nContext: {context}"
            if context else f"{_ROLE_BRIEFING}\n\nSecurity Prompt"
        )
