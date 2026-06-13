import json
import pytest
from pydantic import ValidationError

from config.settings import Settings, MCPServerConfig, ReliabilityConfig, EmbeddingSettings, MemoryConfig, _reset_settings


# Minimal valid env vars required by Settings
REQUIRED_ENV = {
    "TENANT_ID": "test-tenant",
    "LLM__PROVIDER": "anthropic",
    "LLM__MODEL": "claude-sonnet-4-6",
    "LLM__API_KEY": "sk-test",
    "LANGFUSE__PUBLIC_KEY": "pk-test",
    "LANGFUSE__SECRET_KEY": "sk-test",
}


@pytest.fixture(autouse=True)
def reset_settings_singleton():
    _reset_settings()
    yield
    _reset_settings()


@pytest.fixture
def base_env(monkeypatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("MCP_SERVERS", raising=False)


# Optional env vars that may leak from a real .env into the test process.
# We clear these so that defaults and absence tests are reliable.
_OPTIONAL_ENV = [
    "LLM__BASE_URL", "LLM__MAX_TOKENS", "LLM__TEMPERATURE",
    "LANGFUSE__HOST",
    "AGENT__NAME", "AGENT__VERSION", "AGENT__PROMPT_VERSION", "AGENT__MAX_ITERATIONS",
    "ENVIRONMENT", "MCP_SERVERS",
    "RELIABILITY__MAX_TOKENS_PER_RUN", "RELIABILITY__MCP_RETRY_ATTEMPTS",
    "RELIABILITY__MCP_RETRY_BASE_DELAY", "RELIABILITY__CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "RELIABILITY__CIRCUIT_BREAKER_RESET_TIMEOUT", "RELIABILITY__CONTEXT_WINDOW_THRESHOLD",
    "RELIABILITY__HITL_ENABLED",
    "EMBEDDING__MODEL", "EMBEDDING__API_KEY", "EMBEDDING__DIMENSIONS",
    "MEMORY__ENABLED", "MEMORY__SCOPE", "MEMORY__TOP_K", "MEMORY__COLLECTION_NAME",
    "MEMORY__QDRANT_URL", "MEMORY__QDRANT_API_KEY",
]


def make_settings(monkeypatch, extra: dict | None = None) -> Settings:
    for key in _OPTIONAL_ENV:
        monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    if extra:
        for key, value in extra.items():
            monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


class TestSettingsLoad:
    def test_loads_required_fields(self, monkeypatch):
        s = make_settings(monkeypatch)
        assert s.tenant_id == "test-tenant"
        assert s.llm.provider == "anthropic"
        assert s.llm.model == "claude-sonnet-4-6"
        assert s.llm.api_key == "sk-test"
        assert s.langfuse.public_key == "pk-test"

    def test_defaults_applied(self, monkeypatch):
        s = make_settings(monkeypatch)
        assert s.environment == "development"
        assert s.llm.max_tokens == 4096
        assert s.llm.temperature == 0.0
        assert s.agent.name == "ai-agent"
        assert s.agent.prompt_version == "v1"
        assert s.agent.max_iterations == 10
        assert s.mcp_servers == []

    def test_nested_delimiter_works(self, monkeypatch):
        s = make_settings(monkeypatch, {"LLM__MAX_TOKENS": "2048", "LLM__TEMPERATURE": "0.5"})
        assert s.llm.max_tokens == 2048
        assert s.llm.temperature == 0.5

    def test_agent_config_overrideable(self, monkeypatch):
        s = make_settings(monkeypatch, {
            "AGENT__NAME": "certify-agent",
            "AGENT__PROMPT_VERSION": "v2",
            "AGENT__MAX_ITERATIONS": "20",
        })
        assert s.agent.name == "certify-agent"
        assert s.agent.prompt_version == "v2"
        assert s.agent.max_iterations == 20

    def test_langfuse_custom_host(self, monkeypatch):
        s = make_settings(monkeypatch, {"LANGFUSE__HOST": "http://localhost:3000"})
        assert s.langfuse.host == "http://localhost:3000"

    def test_llm_base_url_optional(self, monkeypatch):
        s = make_settings(monkeypatch)
        assert s.llm.base_url is None

    def test_llm_base_url_set(self, monkeypatch):
        s = make_settings(monkeypatch, {"LLM__BASE_URL": "https://openrouter.ai/api/v1"})
        assert s.llm.base_url == "https://openrouter.ai/api/v1"


class TestSettingsValidation:
    def test_missing_tenant_id_raises(self, monkeypatch):
        for key, value in REQUIRED_ENV.items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("TENANT_ID")
        with pytest.raises(ValidationError, match="tenant_id"):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_missing_llm_api_key_raises(self, monkeypatch):
        for key, value in REQUIRED_ENV.items():
            monkeypatch.setenv(key, value)
        monkeypatch.delenv("LLM__API_KEY")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)  # type: ignore[call-arg]

    def test_invalid_llm_provider_raises(self, monkeypatch):
        with pytest.raises(ValidationError):
            make_settings(monkeypatch, {"LLM__PROVIDER": "gemini"})

    def test_invalid_environment_raises(self, monkeypatch):
        with pytest.raises(ValidationError):
            make_settings(monkeypatch, {"ENVIRONMENT": "staging"})

    def test_openrouter_provider_accepted(self, monkeypatch):
        s = make_settings(monkeypatch, {"LLM__PROVIDER": "openrouter"})
        assert s.llm.provider == "openrouter"

    def test_openai_provider_accepted(self, monkeypatch):
        s = make_settings(monkeypatch, {"LLM__PROVIDER": "openai"})
        assert s.llm.provider == "openai"


class TestMCPServerConfig:
    def test_stdio_server_parses(self, monkeypatch):
        servers = [{"name": "fs", "transport": "stdio", "command": "npx", "args": ["-y", "@mcp/server"]}]
        s = make_settings(monkeypatch, {"MCP_SERVERS": json.dumps(servers)})
        assert len(s.mcp_servers) == 1
        assert s.mcp_servers[0].name == "fs"
        assert s.mcp_servers[0].transport == "stdio"
        assert s.mcp_servers[0].args == ["-y", "@mcp/server"]

    def test_http_server_parses(self, monkeypatch):
        servers = [{"name": "remote", "transport": "http", "url": "http://localhost:8080"}]
        s = make_settings(monkeypatch, {"MCP_SERVERS": json.dumps(servers)})
        assert s.mcp_servers[0].url == "http://localhost:8080"

    def test_multiple_servers_parse(self, monkeypatch):
        servers = [
            {"name": "fs", "transport": "stdio", "command": "npx"},
            {"name": "api", "transport": "http", "url": "http://localhost:9000"},
        ]
        s = make_settings(monkeypatch, {"MCP_SERVERS": json.dumps(servers)})
        assert len(s.mcp_servers) == 2

    def test_stdio_without_command_raises(self):
        with pytest.raises(ValidationError, match="command is required"):
            MCPServerConfig(name="bad", transport="stdio")

    def test_http_without_url_raises(self):
        with pytest.raises(ValidationError, match="url is required"):
            MCPServerConfig(name="bad", transport="http")

    def test_sse_without_url_raises(self):
        with pytest.raises(ValidationError, match="url is required"):
            MCPServerConfig(name="bad", transport="sse")

    def test_server_env_vars_parsed(self, monkeypatch):
        servers = [{"name": "fs", "transport": "stdio", "command": "npx", "env": {"HOME": "/tmp"}}]
        s = make_settings(monkeypatch, {"MCP_SERVERS": json.dumps(servers)})
        assert s.mcp_servers[0].env == {"HOME": "/tmp"}


class TestReliabilityConfig:
    def test_reliability_defaults(self, monkeypatch):
        s = make_settings(monkeypatch)
        r = s.reliability
        assert r.max_tokens_per_run == 50_000
        assert r.mcp_retry_attempts == 3
        assert r.mcp_retry_base_delay == 1.0
        assert r.circuit_breaker_failure_threshold == 5
        assert r.circuit_breaker_reset_timeout == 60.0
        assert r.context_window_threshold == 6_000
        assert r.hitl_enabled is False

    def test_reliability_overrideable_via_env(self, monkeypatch):
        s = make_settings(monkeypatch, {
            "RELIABILITY__MAX_TOKENS_PER_RUN": "100000",
            "RELIABILITY__MCP_RETRY_ATTEMPTS": "5",
            "RELIABILITY__HITL_ENABLED": "true",
        })
        assert s.reliability.max_tokens_per_run == 100_000
        assert s.reliability.mcp_retry_attempts == 5
        assert s.reliability.hitl_enabled is True

    def test_reliability_circuit_breaker_overrideable(self, monkeypatch):
        s = make_settings(monkeypatch, {
            "RELIABILITY__CIRCUIT_BREAKER_FAILURE_THRESHOLD": "10",
            "RELIABILITY__CIRCUIT_BREAKER_RESET_TIMEOUT": "120.0",
        })
        assert s.reliability.circuit_breaker_failure_threshold == 10
        assert s.reliability.circuit_breaker_reset_timeout == 120.0

    def test_reliability_context_window_overrideable(self, monkeypatch):
        s = make_settings(monkeypatch, {"RELIABILITY__CONTEXT_WINDOW_THRESHOLD": "8000"})
        assert s.reliability.context_window_threshold == 8_000

    def test_reliability_config_standalone(self):
        r = ReliabilityConfig()
        assert r.max_tokens_per_run == 50_000
        assert r.hitl_enabled is False

    def test_reliability_config_custom_values(self):
        r = ReliabilityConfig(
            max_tokens_per_run=10_000,
            mcp_retry_attempts=1,
            hitl_enabled=True,
        )
        assert r.max_tokens_per_run == 10_000
        assert r.mcp_retry_attempts == 1
        assert r.hitl_enabled is True


class TestEmbeddingSettings:
    def test_embedding_defaults(self, monkeypatch):
        s = make_settings(monkeypatch)
        e = s.embedding
        assert e.model == "text-embedding-3-small"
        assert e.api_key is None
        assert e.dimensions == 1536

    def test_embedding_model_overrideable(self, monkeypatch):
        s = make_settings(monkeypatch, {"EMBEDDING__MODEL": "text-embedding-ada-002"})
        assert s.embedding.model == "text-embedding-ada-002"

    def test_embedding_api_key_overrideable(self, monkeypatch):
        s = make_settings(monkeypatch, {"EMBEDDING__API_KEY": "sk-embed-key"})
        assert s.embedding.api_key == "sk-embed-key"

    def test_embedding_dimensions_overrideable(self, monkeypatch):
        s = make_settings(monkeypatch, {"EMBEDDING__DIMENSIONS": "768"})
        assert s.embedding.dimensions == 768

    def test_embedding_standalone(self):
        e = EmbeddingSettings(model="custom-model", dimensions=512)
        assert e.model == "custom-model"
        assert e.dimensions == 512


class TestMemoryConfig:
    def test_memory_defaults(self, monkeypatch):
        s = make_settings(monkeypatch)
        m = s.memory
        assert m.enabled is False
        assert m.scope == "user"
        assert m.top_k == 5
        assert m.collection_name == "agent_memories"
        assert m.qdrant_url == "http://localhost:6333"
        assert m.qdrant_api_key is None

    def test_memory_enabled_via_env(self, monkeypatch):
        s = make_settings(monkeypatch, {"MEMORY__ENABLED": "true"})
        assert s.memory.enabled is True

    def test_memory_scope_overrideable(self, monkeypatch):
        for scope in ("session", "user", "tenant", "global"):
            s = make_settings(monkeypatch, {"MEMORY__SCOPE": scope})
            assert s.memory.scope == scope

    def test_memory_top_k_overrideable(self, monkeypatch):
        s = make_settings(monkeypatch, {"MEMORY__TOP_K": "10"})
        assert s.memory.top_k == 10

    def test_memory_qdrant_url_overrideable(self, monkeypatch):
        s = make_settings(monkeypatch, {"MEMORY__QDRANT_URL": "http://qdrant:6333"})
        assert s.memory.qdrant_url == "http://qdrant:6333"

    def test_memory_config_standalone(self):
        m = MemoryConfig(enabled=True, scope="tenant", top_k=3)
        assert m.enabled is True
        assert m.scope == "tenant"
        assert m.top_k == 3
