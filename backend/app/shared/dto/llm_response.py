from dataclasses import dataclass


@dataclass(slots=True)
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
