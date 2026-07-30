"""context_extractor.py — Shared slim-context extraction for prompt builders.

All LLM prompt builders that receive a predecessor artifact as context use this
mixin to extract only the fields their stage actually needs, rather than passing
the full accumulated artifact JSON verbatim.

Why this matters
----------------
Full artifacts grow through the pipeline:
  ProductOwner  ~4 KB   (~1,000 tokens)
  Architect     ~8 KB   (~2,000 tokens)
  Designer      ~15 KB  (~3,750 tokens)
  FilePlanner   ~6 KB   (~1,500 tokens)
  Combined      ~30 KB  (~7,500 tokens)  ← Document stage receives all of this

On a model with 8,192-token context (e.g. Ollama qwen2.5-coder:7b), passing the
full artifact chain leaves fewer than 700 tokens for the model's actual output —
guaranteed truncation. The slim-context approach extracts 10-20% of the artifact
that each stage genuinely needs, recovering 3,000–7,000 tokens of output space.

Usage
-----
    from .context_extractor import SlimContextExtractor

    class MyBuilder(PromptBuilder, SlimContextExtractor):
        _SLIM_KEYS = frozenset({"project_name", "tech_stack", "modules"})

        def build(self, context=None) -> str:
            raw = getattr(context, "content", "") or (context if isinstance(context, str) else "")
            slim = self.extract(raw, self._SLIM_KEYS)
            body = f"Context:\n{slim}" if slim else f"Raw:\n{raw[:2000]}"
            return f"{SYSTEM_PROMPT}\n\n{body}"
"""
from __future__ import annotations

import json
import re
from typing import FrozenSet

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJ   = re.compile(r"\{.*\}", re.DOTALL)

# Cap values applied to specific list fields to keep token count bounded.
_LIST_CAPS: dict[str, int] = {
    "api_endpoints": 30,
    "modules":       20,
    "components":    25,
    "data_models":   20,
    "user_flows":    15,
    "page_layouts":  15,
    "requirements":  15,
    "written_paths": 50,
}

# For api_endpoints we only keep name/method/path — other fields (description,
# request_body, response_schema) are not needed by any downstream stage.
_API_ENDPOINT_SLIM_KEYS = ("name", "method", "path")


class SlimContextExtractor:
    """Mixin for prompt builders that extract a slim subset of a predecessor artifact.

    Subclasses declare ``_SLIM_KEYS`` (a frozenset of JSON keys to keep) and call
    ``self.extract(raw_text, keys)`` inside their ``build()`` method.

    The extraction logic is intentionally simple and deterministic:
    - Tries to parse the full text as JSON (handles markdown fences).
    - Looks for a nested "structured" key (artifact file format) and falls back
      to the top-level dict (raw LLM response format).
    - Picks only the keys listed in ``keys``.
    - Applies list-length caps and field-level trimming (api_endpoints → name/method/path).
    - Returns an empty string if parsing fails; callers should fall back to raw[:N].
    """

    @staticmethod
    def parse_artifact_json(text: str) -> dict:
        """Parse the first JSON object from ``text``, handling markdown fences.

        Returns an empty dict on any parse failure — never raises.
        """
        candidates: list[str | None] = [
            _JSON_FENCE.search(text) and _JSON_FENCE.search(text).group(1),  # type: ignore[union-attr]
            _JSON_OBJ.search(text) and _JSON_OBJ.search(text).group(0),      # type: ignore[union-attr]
            text,
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except (ValueError, TypeError):
                continue
        return {}

    @staticmethod
    def _unwrap_structured(raw: dict) -> dict:
        """Artifact files wrap LLM output under a "structured" key.

        If present and non-empty, unwrap it. Otherwise treat the top-level dict
        as the structured data directly (raw LLM response shape).
        """
        structured = raw.get("structured")
        if isinstance(structured, dict) and structured:
            return structured
        return raw

    def extract(self, text: str, keys: FrozenSet[str]) -> str:
        """Extract ``keys`` from ``text`` and return compact JSON, or '' on failure."""
        raw = self.parse_artifact_json(text)
        if not raw:
            return ""
        structured = self._unwrap_structured(raw)
        slim: dict = {k: structured[k] for k in keys if k in structured}
        if not slim:
            return ""

        # Apply field-level trimming
        self._trim_fields(slim)

        return json.dumps(slim, indent=2)

    @staticmethod
    def _trim_fields(slim: dict) -> None:
        """In-place: apply list caps and field-level slim for known heavy fields."""
        for field, cap in _LIST_CAPS.items():
            if field in slim and isinstance(slim[field], list):
                slim[field] = slim[field][:cap]

        # api_endpoints: keep only routing fields, not full request/response schemas
        if "api_endpoints" in slim and isinstance(slim["api_endpoints"], list):
            slim["api_endpoints"] = [
                {k: ep.get(k, "") for k in _API_ENDPOINT_SLIM_KEYS}
                for ep in slim["api_endpoints"]
                if isinstance(ep, dict)
            ]

        # requirements: keep only name + description (drop acceptance_criteria, etc.)
        if "requirements" in slim and isinstance(slim["requirements"], list):
            slim["requirements"] = [
                {
                    "name": r.get("name") or r.get("title") or "",
                    "description": str(r.get("description") or r.get("summary") or "")[:200],
                }
                if isinstance(r, dict) else str(r)[:200]
                for r in slim["requirements"]
            ]

    @staticmethod
    def get_raw_content(context: object | None) -> str:
        """Pull the raw text out of a context object (supports .content attr or str)."""
        if context is None:
            return ""
        raw = getattr(context, "content", None)
        if raw is not None:
            return str(raw)
        if isinstance(context, str):
            return context
        return str(context)
