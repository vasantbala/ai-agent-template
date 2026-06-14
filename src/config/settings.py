from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    provider: Literal["openai", "anthropic", "openrouter"]
    model: str
    api_key: str
    base_url: str | None = None  # override for OpenRouter / LiteLLM proxy
    max_tokens: int = 4096
    temperature: float = 0.0


class LangfuseSettings(BaseModel):
    public_key: str
    secret_key: str
    host: str = "https://cloud.langfuse.com"


class MCPServerConfig(BaseModel):
    name: str
    transport: Literal["stdio", "sse", "http"]
    command: str | None = None  # required for stdio
    args: list[str] = []
    url: str | None = None  # required for sse/http
    env: dict[str, str] = {}

    @model_validator(mode="after")
    def validate_transport_fields(self) -> MCPServerConfig:
        if self.transport == "stdio" and not self.command:
            raise ValueError("command is required for stdio transport")
        if self.transport in ("sse", "http") and not self.url:
            raise ValueError("url is required for sse/http transport")
        return self


class SubAgentConfig(BaseModel):
    name: str
    url: str
    description: str
    timeout: float = 30.0


class AgentConfig(BaseModel):
    name: str = "ai-agent"
    version: str = "1.0.0"
    prompt_version: str = "v1"  # maps to prompts/{version}/system.md
    max_iterations: int = 10
    sub_agents: list[SubAgentConfig] = []


class ReliabilityConfig(BaseModel):
    max_tokens_per_run: int = 50_000
    mcp_retry_attempts: int = 3
    mcp_retry_base_delay: float = 1.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_reset_timeout: float = 60.0
    context_window_threshold: int = 6_000
    hitl_enabled: bool = False


class CostConfig(BaseModel):
    enabled: bool = True


class ScheduleConfig(BaseModel):
    enabled: bool = False
    cron: str = "0 9 * * *"
    input: str = ""
    tenant_id: str = ""
    session_id_prefix: str = "scheduled"


class EvalConfig(BaseModel):
    enabled: bool = False
    metrics: list[Literal["correctness", "faithfulness", "relevancy"]] = ["correctness"]
    threshold: float = 0.7
    model: str = "gpt-4o"
    golden_dataset_path: str = "evals/golden/default.json"


class EmbeddingSettings(BaseModel):
    model: str = "text-embedding-3-small"
    api_key: str | None = None  # falls back to LLM api_key when None
    dimensions: int = 1536


class MemoryConfig(BaseModel):
    enabled: bool = False
    scope: Literal["session", "user", "tenant", "global"] = "user"
    top_k: int = 5
    collection_name: str = "agent_memories"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None


class Settings(BaseSettings):
    tenant_id: str
    environment: Literal["development", "production"] = "development"
    llm: LLMSettings
    langfuse: LangfuseSettings
    agent: AgentConfig = AgentConfig()
    mcp_servers: list[MCPServerConfig] = []
    reliability: ReliabilityConfig = ReliabilityConfig()
    embedding: EmbeddingSettings = EmbeddingSettings()
    memory: MemoryConfig = MemoryConfig()
    eval: EvalConfig = EvalConfig()
    cost: CostConfig = CostConfig()
    schedule: ScheduleConfig = ScheduleConfig()

    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def _reset_settings() -> None:
    """Reset the singleton — for use in tests only."""
    global _settings
    _settings = None
