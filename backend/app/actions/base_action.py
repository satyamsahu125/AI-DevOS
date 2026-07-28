from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_MISSING_COMMA = re.compile(r'"(\s*\n\s*)"(?=[^"\\]*"\s*:)')


class ActionOutput(BaseModel):
    """Result of running a BaseAction: the raw text plus whatever structured data could be parsed from it."""

    content: str
    structured: dict[str, Any] = {}
    tokens_used: int = 0
    latency_ms: float = 0.0


class BaseAction(ABC):
    """A single LLM-backed unit of work an agent performs.

    Inspired by MetaGPT's Action, adapted to run synchronously: AI DevOS's
    agents, workflow engine, and execution pipeline are all synchronous
    today, so making Action.run() async would mean threading asyncio
    through the whole call chain just to match MetaGPT's shape. Running it
    sync is the "your way" adaptation the integration calls for.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def run(self, context: object, llm: object) -> ActionOutput:
        """Run this action against context using llm, returning its ActionOutput."""
        raise NotImplementedError

    @staticmethod
    def extract_json(text: str) -> dict[str, Any]:
        """Best-effort extraction of a JSON object from LLM text.

        Tries, in order:
        1. Whole text as JSON
        2. ```json fenced block
        3. First {...} span
        Each candidate is retried through _repair_common_json_errors() if the
        raw parse fails (missing commas between pairs on adjacent lines).
        If all clean candidates fail, tries _complete_truncated_json() which
        closes any unclosed string/array/object left by a token-limit cutoff
        — this recovers partial JSON from models that run out of tokens
        mid-generation (observed with qwen2.5-coder:7b on complex schemas).
        Returns {} if nothing parses.
        """
        for candidate in BaseAction._json_candidates(text):
            # Try raw, then comma-repaired, then truncation-completed variants
            for attempt in (
                candidate,
                BaseAction._repair_common_json_errors(candidate),
                BaseAction._complete_truncated_json(candidate),
                BaseAction._complete_truncated_json(
                    BaseAction._repair_common_json_errors(candidate)
                ),
            ):
                if not attempt:
                    continue
                try:
                    parsed = json.loads(attempt)
                except (ValueError, TypeError):
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return {}

    @staticmethod
    def _repair_common_json_errors(text: str) -> str:
        """Insert a missing comma between two adjacent "key": "value" pairs split across lines --
        the single most common syntax slip observed from local models (e.g. qwen2.5-coder), where a
        long string value's closing quote is immediately followed by the next field's opening quote
        with no comma in between."""
        return _MISSING_COMMA.sub(r'",\1"', text)

    @staticmethod
    def _complete_truncated_json(text: str) -> str:
        """Complete a JSON object that was cut off mid-stream (token-limit truncation).

        Uses a stack to track the exact nesting order of open `{` and `[`
        tokens, then closes them in reverse order. This is necessary because
        flat depth counters produce wrong results for interleaved structures
        like `[{"key": "val` where `}` must come before `]`.

        Also strips trailing whitespace before closing an open string, since
        a literal newline inside a JSON string value is invalid.

        Returns the original string unchanged if already balanced, or an
        empty string if there is no opening `{` to anchor recovery.
        """
        start = text.find("{")
        if start < 0:
            return ""
        partial = text[start:]

        stack: list[str] = []   # '{' or '[' in order of appearance
        in_string = False
        escaped = False

        for ch in partial:
            if escaped:
                escaped = False
                continue
            if ch == "\\" and in_string:
                escaped = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in "{[":
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()

        # Already balanced — nothing to do
        if not in_string and not stack:
            return partial

        # Close open string first (strip trailing whitespace to avoid
        # embedding a literal newline, which is invalid in JSON strings).
        base = partial.rstrip() if in_string else partial
        suffix = '"' if in_string else ""
        # Close structures in reverse nesting order
        for opener in reversed(stack):
            suffix += "}" if opener == "{" else "]"
        return base + suffix

    @staticmethod
    def _json_candidates(text: str):
        if not text:
            return
        yield text
        fence_match = _JSON_FENCE.search(text)
        if fence_match:
            yield fence_match.group(1)
        object_match = _JSON_OBJECT.search(text)
        if object_match:
            yield object_match.group(0)


class LLMAction(BaseAction):
    """BaseAction that builds a prompt via a PromptBuilder, calls the LLM, and parses the response into schema_model."""

    schema_model: type[BaseModel] | None = None
    system_prompt: str = ""
    # When True (default for all structured-output actions), the Ollama
    # provider enables grammar-constrained JSON decoding (format="json").
    # This guarantees syntactically valid JSON even when the model hits its
    # token limit, eliminating the "key: <EOF>" truncation class that
    # _complete_truncated_json cannot recover. Set to False only for actions
    # that produce free-form text (e.g. changelog summaries).
    output_json: bool = True

    def __init__(self, prompt_builder: Any) -> None:
        """Wire the PromptBuilder used to turn context content into a prompt."""
        self.prompt_builder = prompt_builder

    def run(self, context: object, llm: object) -> ActionOutput:
        """Build the prompt, call llm.generate_text(), and parse+validate the structured response."""
        content = getattr(context, "content", "") if context is not None else ""
        project_id = getattr(context, "project_id", "") if context is not None else ""
        prompt = self.prompt_builder.build(content)
        logger.info("%s running", self.name)

        started = time.time()
        response = llm.generate_text(
            prompt,
            system_prompt=self.system_prompt,
            stage=self.name,
            agent=self.name,
            project_id=project_id,
            json_mode=self.output_json,
        )
        elapsed_ms = (time.time() - started) * 1000

        structured = self._parse_structured(response.content)
        tokens_used = self._extract_tokens(response)
        latency_ms = self._extract_latency_ms(response, elapsed_ms)

        logger.debug(
            "%s completed: tokens=%s latency_ms=%.1f structured=%s",
            self.name, tokens_used, latency_ms, bool(structured),
        )
        return ActionOutput(content=response.content, structured=structured, tokens_used=tokens_used, latency_ms=latency_ms)

    def _parse_structured(self, text: str) -> dict[str, Any]:
        if self.schema_model is None:
            return {}
        raw = self.extract_json(text)
        if not raw:
            return {}
        normalized = {}
        for k, v in raw.items():
            snake_k = re.sub(r'(?<!^)(?=[A-Z])', '_', k).lower()
            normalized[snake_k] = v
        try:
            return self.schema_model.model_validate(normalized).model_dump(mode="json")
        except Exception:
            try:
                return self.schema_model.model_validate(raw).model_dump(mode="json")
            except Exception as exc:
                logger.debug("%s structured output failed schema validation: %s", self.name, exc)
                return {}

    def _extract_tokens(self, response: object) -> int:
        total = getattr(response, "total_tokens", None)
        if total is not None:
            return int(total)
        usage = getattr(response, "usage", None) or {}
        return int(usage.get("total", 0))

    def _extract_latency_ms(self, response: object, fallback_ms: float) -> float:
        latency = getattr(response, "latency", None)
        if latency:
            return latency * 1000
        return fallback_ms
