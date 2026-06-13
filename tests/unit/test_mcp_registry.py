import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from config.settings import MCPServerConfig
from tools.registry import MCPRegistry
from tools.client import MCPClient


def make_stdio_config(name: str = "fs") -> MCPServerConfig:
    return MCPServerConfig(name=name, transport="stdio", command="npx")


def make_http_config(name: str = "api") -> MCPServerConfig:
    return MCPServerConfig(name=name, transport="http", url="http://localhost:8080")


def make_mock_client(tools: list[dict] | None = None) -> AsyncMock:
    client = AsyncMock(spec=MCPClient)
    client.list_tools.return_value = tools or [
        {"type": "function", "function": {"name": "search", "description": "Search", "parameters": {}}},
    ]
    client.call_tool.return_value = "tool result"
    return client


class TestMCPRegistry:
    def test_initialises_clients_from_configs(self):
        registry = MCPRegistry([make_stdio_config("a"), make_stdio_config("b")])
        assert registry.connected_servers == ["a", "b"]

    def test_empty_config_creates_empty_registry(self):
        registry = MCPRegistry([])
        assert registry.connected_servers == []

    async def test_connect_all_calls_connect_on_each_client(self):
        registry = MCPRegistry([make_stdio_config("fs"), make_http_config("api")])
        mock_fs = make_mock_client([{"type": "function", "function": {"name": "read_file", "description": "", "parameters": {}}}])
        mock_api = make_mock_client([{"type": "function", "function": {"name": "search", "description": "", "parameters": {}}}])
        registry._clients = {"fs": mock_fs, "api": mock_api}

        await registry.connect_all()

        mock_fs.connect.assert_awaited_once()
        mock_api.connect.assert_awaited_once()

    async def test_connect_all_builds_tool_to_server_map(self):
        registry = MCPRegistry([make_stdio_config("fs")])
        mock_client = make_mock_client([
            {"type": "function", "function": {"name": "read_file", "description": "", "parameters": {}}},
            {"type": "function", "function": {"name": "write_file", "description": "", "parameters": {}}},
        ])
        registry._clients = {"fs": mock_client}
        await registry.connect_all()

        assert registry._tool_to_server["read_file"] == "fs"
        assert registry._tool_to_server["write_file"] == "fs"

    async def test_disconnect_all_calls_disconnect_on_each_client(self):
        registry = MCPRegistry([make_stdio_config("fs")])
        mock_client = make_mock_client()
        registry._clients = {"fs": mock_client}

        await registry.disconnect_all()
        mock_client.disconnect.assert_awaited_once()

    async def test_get_all_tools_merges_from_all_servers(self):
        registry = MCPRegistry([make_stdio_config("fs"), make_http_config("api")])
        mock_fs = make_mock_client([{"type": "function", "function": {"name": "read_file", "description": "", "parameters": {}}}])
        mock_api = make_mock_client([{"type": "function", "function": {"name": "search", "description": "", "parameters": {}}}])
        registry._clients = {"fs": mock_fs, "api": mock_api}

        tools = await registry.get_all_tools()
        names = [t["function"]["name"] for t in tools]
        assert "read_file" in names
        assert "search" in names

    async def test_call_tool_routes_to_correct_server(self):
        registry = MCPRegistry([make_stdio_config("fs"), make_http_config("api")])
        mock_fs = make_mock_client()
        mock_api = make_mock_client()
        registry._clients = {"fs": mock_fs, "api": mock_api}
        registry._tool_to_server = {"read_file": "fs", "search": "api"}

        await registry.call_tool("read_file", {"path": "/tmp/file.txt"})

        mock_fs.call_tool.assert_awaited_once_with("read_file", {"path": "/tmp/file.txt"})
        mock_api.call_tool.assert_not_awaited()

    async def test_call_unknown_tool_raises(self):
        registry = MCPRegistry([make_stdio_config("fs")])
        registry._clients = {}
        registry._tool_to_server = {}

        with pytest.raises(ValueError, match="Unknown tool"):
            await registry.call_tool("nonexistent", {})

    async def test_call_tool_error_includes_available_tools(self):
        registry = MCPRegistry([])
        registry._tool_to_server = {"read_file": "fs"}

        with pytest.raises(ValueError, match="nonexistent"):
            await registry.call_tool("nonexistent", {})
