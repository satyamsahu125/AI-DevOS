from __future__ import annotations

import json
from urllib.request import Request, urlopen

from ..provider import BaseLLMProvider
from ..request import LLMRequest
from ..response import LLMResponse


class OllamaProvider(BaseLLMProvider):
    """Provider implementation that calls a local Ollama server."""

    def __init__(self, host: str = "http://localhost:11434") -> None:
        self.host = host.rstrip("/")

    def generate(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": request.model,
            "prompt": request.user_prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if request.system_prompt:
            payload["system"] = request.system_prompt

        req = Request(
            f"{self.host}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")

        data = json.loads(body)
        return LLMResponse(
            content=data.get("response", ""),
            model=request.model,
            finish_reason=data.get("done", True) and "stop" or "length",
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
            total_tokens=int(data.get("prompt_eval_count", 0)) + int(data.get("eval_count", 0)),
        )
