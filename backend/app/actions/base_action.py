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

        Tries, in order: the whole text as JSON, a ```json fenced block,
        then the first balanced-looking {...} span -- each candidate is also
        retried through _repair_common_json_errors() if the raw parse fails,
        since local models reliably produce one specific mistake (a missing
        comma between two "key": "value" pairs split across lines). Returns
        {} if nothing parses -- callers must treat an empty dict as "no
        structured output", not an error.
        """
        for candidate in BaseAction._json_candidates(text):
            try:
                parsed = json.loads(candidate)
            except (ValueError, TypeError):
                try:
                    parsed = json.loads(BaseAction._repair_common_json_errors(candidate))
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
        response = llm.generate_text(prompt, system_prompt=self.system_prompt, stage=self.name, agent=self.name, project_id=project_id)
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
