from __future__ import annotations

from typing import Any

from config.settings import MCPServerConfig
from tools.client import MCPClient


class MCPRegistry:
    def __init__(self, configs: list[MCPServerConfig]):
        self._clients: dict[str, MCPClient] = {
            cfg.name: MCPClient(cfg) for cfg in configs
        }
        self._tool_to_server: dict[str, str] = {}

    async def connect_all(self) -> None:
        for name, client in self._clients.items():
            await client.connect()
            tools = await client.list_tools()
            for tool in tools:
                self._tool_to_server[tool["function"]["name"]] = name

    async def disconnect_all(self) -> None:
        for client in self._clients.values():
            await client.disconnect()

    async def get_all_tools(self) -> list[dict[str, Any]]:
        tools = []
        for client in self._clients.values():
            tools.extend(await client.list_tools())
        return tools

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        server_name = self._tool_to_server.get(name)
        if not server_name:
            raise ValueError(
                f"Unknown tool '{name}'. "
                f"Available tools: {list(self._tool_to_server)}"
            )
        return await self._clients[server_name].call_tool(name, args)

    @property
    def connected_servers(self) -> list[str]:
        return list(self._clients)
