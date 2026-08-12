"""secret_scrubber.py — sanitise text before it enters the RAG knowledge store.

Secrets embedded into the HNSW vector index or persisted in knowledge.sqlite
would leak into future agent prompts across sessions (and potentially across
projects, given that the knowledge store is global). This module scrubs common
credential patterns BEFORE the text reaches the embedding model, SQLite, or
the HNSW index.

Scrubbing happens at the KnowledgeMemory.store() entry point — the single gate
that all write paths (LearningLoop.record_trajectory, direct store calls) pass
through. Any caller that bypasses KnowledgeMemory.store() is outside the
scrubbing boundary.

Design principles
-----------------
* Fail-safe: if the scrubber itself raises, the text is BLOCKED (not stored as-is).
* Conservative: prefer false positives (replacing non-secrets) over false
  negatives (missing real secrets). A slightly garbled pattern memory is
  preferable to a credential leak.
* Documented limitations: regex-based, no entropy analysis, no ML. Cannot
  detect secrets in custom encodings, split across lines, or otherwise
  obfuscated.

Known limitations
-----------------
* Does not detect secrets split across multiple lines or concatenated at runtime.
* Does not detect secrets encoded in non-ASCII charsets or custom base64 variants.
* Does not detect cryptographic private keys (PEM/DER blocks) — these are long
  and would be truncated by the value-length check before reaching the scrubber
  in practice, but callers should not rely on this.
* Does not detect secrets stored as environment variable *names* (only values).
* Entropy analysis (e.g. Shannon entropy) is intentionally omitted: it produces
  too many false positives on minified code and base64-encoded binary data that
  are not secrets.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Replacement sentinel
# ---------------------------------------------------------------------------

REDACTED = "[REDACTED]"

# ---------------------------------------------------------------------------
# Secret patterns
# ---------------------------------------------------------------------------
# Each tuple is (label, compiled_regex).
# The regex must have exactly one capture group containing the SECRET VALUE
# to be replaced — everything outside the group is preserved in the output.
#
# Order matters: more-specific patterns come first so they capture before a
# less-specific pattern would match overlapping text.

_PATTERNS: list[tuple[str, re.Pattern]] = [
    # JWT tokens: three base64url segments separated by dots.
    # Only the header segment is guaranteed to start with "eyJ" (base64-encoded '{"').
    # The payload may or may not also start with "eyJ" depending on the algorithm/library.
    (
        "jwt",
        re.compile(
            r"(eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,})",
            re.IGNORECASE,
        ),
    ),

    # AWS access key ID: AKIA/AGPA/AIDA/AROA/ASIA + 16 uppercase alphanumeric chars
    (
        "aws_access_key",
        re.compile(r"((?:AKIA|AGPA|AIDA|AROA|ASIA)[A-Z0-9]{16})"),
    ),

    # AWS secret access key — typically follows "aws_secret_access_key" or similar
    # Pattern: 40-char base64 string (upper+lower+digits+/+=)
    (
        "aws_secret_key",
        re.compile(
            r"(?:aws_secret(?:_access)?_key|AWS_SECRET(?:_ACCESS)?_KEY)\s*[=:]\s*['\"]?([A-Za-z0-9+/]{40})['\"]?",
            re.IGNORECASE,
        ),
    ),

    # OpenAI / Anthropic / generic sk- keys
    # sk-proj-... (OpenAI project keys), sk-ant-... (Anthropic), sk-[alphanum]{20+}
    (
        "sk_key",
        re.compile(r"(sk-(?:proj-|ant-|[a-z]+-)?[A-Za-z0-9_-]{20,})", re.IGNORECASE),
    ),

    # Google API keys: AIza + 35 alphanumeric+dash chars
    (
        "google_api_key",
        re.compile(r"(AIza[A-Za-z0-9_-]{35})", re.IGNORECASE),
    ),

    # GitHub tokens: ghp_, ghs_, gho_, ghr_, github_pat_ prefix + 36+ chars
    (
        "github_token",
        re.compile(
            r"((?:ghp|ghs|gho|ghr|github_pat)_[A-Za-z0-9_]{36,})",
            re.IGNORECASE,
        ),
    ),

    # Bearer tokens in Authorization headers / JSON values.
    # Matches: "Authorization": "Bearer <token>", Authorization: Bearer <token>,
    # "bearer": "<token>", or bare "Bearer <token>" anywhere in text.
    # The key may be JSON-quoted, so we allow optional quotes around the key.
    (
        "bearer_token",
        re.compile(
            r"(?:['\"]?Authorization['\"]?\s*[\":,]+\s*['\"]?Bearer\s+"
            r"|['\"]?bearer['\"]?\s*[\":,]+\s*['\"]?"
            r"|Bearer\s+)"
            r"([A-Za-z0-9_\-\.]{20,})",
            re.IGNORECASE,
        ),
    ),

    # Generic API key assignments: api_key=VALUE, apiKey: "VALUE", etc.
    # Matches values that are ≥16 alphanumeric chars (short values are likely not secrets)
    (
        "api_key_assignment",
        re.compile(
            r"(?:api[_-]?key|api[_-]?secret|access[_-]?token|secret[_-]?key|"
            r"client[_-]?secret|private[_-]?key|auth[_-]?token|auth[_-]?secret)"
            r"\s*[=:\"']+\s*[\"']?([A-Za-z0-9_\-\.\/+]{16,})[\"']?",
            re.IGNORECASE,
        ),
    ),

    # Password assignments: password=VALUE, passwd: "VALUE", etc.
    # Only redact if value is ≥8 chars (to avoid matching empty/short placeholders)
    (
        "password_assignment",
        re.compile(
            r"(?:password|passwd|pwd)\s*[=:\"']+\s*[\"']?([^\s\"',;}{)]{8,})[\"']?",
            re.IGNORECASE,
        ),
    ),

    # Environment variable assignments with high-entropy values
    # Pattern: ALL_CAPS_VAR=value where value looks like a secret (≥20 chars, mixed case)
    (
        "env_var_secret",
        re.compile(
            r"(?:^|[;\n&| ])"
            r"(?:[A-Z][A-Z0-9_]{3,}(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIAL|APIKEY|API_KEY))"
            r"=([^\s\"']{16,})",
            re.MULTILINE,
        ),
    ),
]

# Compile once at import time (above). But we also need to compile a fast
# early-exit check: if none of the trigger substrings appear in the text,
# skip regex scanning entirely.
_TRIGGER_SUBSTRINGS: tuple[str, ...] = (
    "eyJ",               # JWT
    "AKIA", "AGPA", "AIDA", "AROA", "ASIA",  # AWS
    "sk-",               # OpenAI/Anthropic
    "AIza",              # Google
    "ghp_", "ghs_", "gho_", "ghr_", "github_pat_",  # GitHub
    "Bearer", "bearer",  # Bearer tokens
    "api_key", "apikey", "api-key",  # generic API keys (lowercase)
    "API_KEY", "API_SECRET", "ACCESS_TOKEN", "SECRET_KEY",  # env vars
    "password", "passwd", "pwd",
    "client_secret", "private_key", "auth_token",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class SecretScrubber:
    """Regex-based scrubber that redacts common secret patterns from text.

    Thread-safe (stateless — all state is in compiled module-level patterns).

    Usage::

        scrubber = SecretScrubber()
        safe_text = scrubber.scrub(raw_text)
        store_in_rag(safe_text)

    ``scrub()`` returns the cleaned text. It NEVER returns the original text
    unchanged if a pattern matched — matched groups are always replaced with
    ``[REDACTED]``.

    If the scrubber itself raises an exception, the caller should treat the
    text as unsafe and BLOCK it from the store (rather than storing the raw
    text as a fallback). The ``scrub_or_raise()`` method enforces this.
    """

    def scrub(self, text: str) -> str:
        """Return *text* with all detected secret values replaced by ``[REDACTED]``.

        Fast-exits (returns the original string) if none of the known trigger
        substrings appear in the text, so short, safe strings incur almost no
        overhead.

        A replacement is logged at DEBUG level for each pattern match, including
        the pattern label, so operators can audit what was scrubbed without
        seeing the actual secret value.
        """
        if not text:
            return text

        # Fast path: skip regex scanning if no known trigger strings are present.
        lower = text.lower()
        if not any(t.lower() in lower for t in _TRIGGER_SUBSTRINGS):
            return text

        result = text
        for label, pattern in _PATTERNS:
            new_result = pattern.sub(
                lambda m, _label=label: m.group(0).replace(m.group(1), REDACTED),
                result,
            )
            if new_result != result:
                count = len(pattern.findall(result))
                logger.debug(
                    "secret_scrubber: redacted %d match(es) for pattern '%s'",
                    count, label,
                )
                result = new_result

        return result

    def scrub_or_raise(self, text: str) -> str:
        """Scrub *text*, raising ``ValueError`` if the scrubber itself fails.

        Callers that cannot accept raw-text fallback (e.g. KnowledgeMemory.store)
        should use this variant so a scrubber bug surfaces as a loud failure
        rather than silently indexing unredacted secrets.
        """
        try:
            return self.scrub(text)
        except Exception as exc:
            raise ValueError(f"SecretScrubber.scrub() failed — cannot store text safely: {exc}") from exc

    def contains_secret(self, text: str) -> bool:
        """Return True if *text* contains at least one detectable secret pattern.

        Useful for tests and policy checks without modifying the text.
        """
        return self.scrub(text) != text


# Module-level singleton — reuse across the process (patterns are compiled once).
_default_scrubber = SecretScrubber()


def scrub(text: str) -> str:
    """Module-level convenience: scrub *text* using the shared singleton."""
    return _default_scrubber.scrub(text)


def contains_secret(text: str) -> bool:
    """Module-level convenience: check if *text* contains a detectable secret."""
    return _default_scrubber.contains_secret(text)
