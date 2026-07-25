from __future__ import annotations

import json
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
        arch_text = ""
        if isinstance(context, dict):
            arch_text = json.dumps(context, indent=2)[:3000]
        elif context:
            arch_text = str(context)[:3000]

        user_prompt = f"""
Perform a security audit of this SPECIFIC architecture:

Architecture Context:
{arch_text}

RULES:
- Reference specific endpoint paths in every finding
- Never write "SQL injection possible in user inputs" (generic)
- Write "POST /api/v1/todos — 'title' field not sanitized"
- If no auth exists: security findings relate to input validation,
  XSS prevention, CORS, rate limiting — not token expiry
- Only find vulnerabilities relevant to what was actually designed
"""
        return f"{_ROLE_BRIEFING}\n\n{user_prompt}"
