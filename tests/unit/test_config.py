import json
import pytest
from pydantic import ValidationError

from config.settings import Settings, MCPServerConfig, _reset_settings


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


def make_settings(monkeypatch, extra: dict | None = None) -> Settings:
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
