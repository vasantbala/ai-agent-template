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


class AgentConfig(BaseModel):
    name: str = "ai-agent"
    version: str = "1.0.0"
    prompt_version: str = "v1"  # maps to prompts/{version}/system.md
    max_iterations: int = 10


class Settings(BaseSettings):
    tenant_id: str
    environment: Literal["development", "production"] = "development"
    llm: LLMSettings
    langfuse: LangfuseSettings
    agent: AgentConfig = AgentConfig()
    mcp_servers: list[MCPServerConfig] = []

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
