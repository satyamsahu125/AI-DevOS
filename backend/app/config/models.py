from __future__ import annotations

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = Field(default="default")
    model: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.0)
    max_tokens: int = Field(default=256)


class RuntimeConfig(BaseModel):
    workspace: str = Field(default="backend/temp-workspace")
    retry_limit: int = Field(default=3)
    log_level: str = Field(default="INFO")


class Settings(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
