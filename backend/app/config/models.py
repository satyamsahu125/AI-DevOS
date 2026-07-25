from __future__ import annotations

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = Field(default="ollama")
    model: str = Field(default="qwen2.5-coder:7b")
    base_url: str = Field(default="http://localhost:11434")
    temperature: float = Field(default=0.1)
    max_tokens: int = Field(default=4096)
    bedrock_api_key: str = Field(default="")
    bedrock_region: str = Field(default="us-east-1")


class RuntimeConfig(BaseModel):
    workspace: str = Field(default="backend/temp-workspace")
    retry_limit: int = Field(default=3)
    log_level: str = Field(default="INFO")


class Settings(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    knowledge_db: str = Field(default="data/knowledge.sqlite")
    learning_db: str = Field(default="data/learning.sqlite")
    memory_db_path: str = Field(default="backend/app/memory/memory.db")
    workspace_root: str = Field(default="temp-workspace")
