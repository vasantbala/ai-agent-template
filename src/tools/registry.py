from __future__ import annotations

from typing import Any

from config.settings import MCPServerConfig, ReliabilityConfig
from reliability.circuit_breaker import CircuitBreaker
from reliability.retry import retry_tool
from tools.client import MCPClient


class MCPRegistry:
    def __init__(
        self,
        configs: list[MCPServerConfig],
        reliability: ReliabilityConfig | None = None,
    ):
        self._clients: dict[str, MCPClient] = {
            cfg.name: MCPClient(cfg) for cfg in configs
        }
        self._tool_to_server: dict[str, str] = {}
        rel = reliability or ReliabilityConfig()
        self._breakers: dict[str, CircuitBreaker] = {
            name: CircuitBreaker(
                name,
                failure_threshold=rel.circuit_breaker_failure_threshold,
                reset_timeout=rel.circuit_breaker_reset_timeout,
            )
            for name in self._clients
        }
        self._retry_attempts = rel.mcp_retry_attempts
        self._retry_base_delay = rel.mcp_retry_base_delay

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
        client = self._clients[server_name]
        breaker = self._breakers[server_name]

        async def _call() -> str:
            return await retry_tool(
                client.call_tool,
                name,
                args,
                max_attempts=self._retry_attempts,
                base_delay=self._retry_base_delay,
            )

        return await breaker.call(_call)

    @property
    def connected_servers(self) -> list[str]:
        return list(self._clients)
