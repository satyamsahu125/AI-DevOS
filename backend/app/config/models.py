from __future__ import annotations

from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    provider: str = Field(default="ollama")
    model: str = Field(default="qwen2.5-coder:7b")
    base_url: str = Field(default="http://localhost:11434")
    temperature: float = Field(default=0.1)
    # 8192 tokens: Architect and BackendDev generate large JSON objects (modules,
    # api_endpoints, data_models, file contents) that routinely exceed 4096 tokens
    # on complex projects. 4096 caused reliable mid-JSON truncation on qwen2.5-coder:7b.
    max_tokens: int = Field(default=8192)
    # Socket timeout in seconds for each LLM call.
    # Designer stage on qwen2.5-coder:7b measured >600s on modest hardware
    # when the accumulated context is large — raising the default prevents
    # spurious TimeoutError failures on slow machines.
    timeout: int = Field(default=1200)
    # Ollama context window (num_ctx). The default Ollama value is 2048 which
    # causes mid-JSON truncation when prompt + response exceed that length.
    # Architect and BackendDev stages routinely need 6000+ combined tokens.
    # Set to 8192 so that num_predict=8192 can actually be used in full.
    num_ctx: int = Field(default=8192)
    bedrock_api_key: str = Field(default="")
    bedrock_region: str = Field(default="us-east-1")
    # API keys for cloud providers.  Set provider="claude" + claude_api_key,
    # or provider="gemini" + gemini_api_key, to route all LLM calls through
    # that provider instead of the local Ollama server.
    claude_api_key: str = Field(default="")
    gemini_api_key: str = Field(default="")


class RuntimeConfig(BaseModel):
    workspace: str = Field(default="backend/temp-workspace")
    retry_limit: int = Field(default=3)
    log_level: str = Field(default="INFO")


class SprintRetryConfig(BaseModel):
    max_dev_review_iterations: int = Field(default=3, description="TechLead → dev loop limit")
    max_qa_iterations: int = Field(default=3, description="dev → QA loop limit")
    max_spec_fix_iterations: int = Field(default=2, description="ProductOwner/Architect update → dev → QA limit")


class Settings(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    knowledge_db: str = Field(default="data/knowledge.sqlite")
    learning_db: str = Field(default="data/learning.sqlite")
    lessons_db: str = Field(default="data/lessons.sqlite")
    memory_db_path: str = Field(default="backend/app/memory/memory.db")
    workspace_root: str = Field(default="temp-workspace")
    sprint_retry: SprintRetryConfig = Field(default_factory=SprintRetryConfig, description="Sprint feedback loop retry limits")
