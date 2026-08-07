from dataclasses import dataclass


@dataclass(slots=True)
class LLMRequest:
    system_prompt: str
    user_prompt: str
    temperature: float
    max_tokens: int
