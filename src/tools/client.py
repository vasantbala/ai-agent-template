from __future__ import annotations

import json
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

from config.settings import MCPServerConfig


class MCPClient:
    def __init__(self, config: MCPServerConfig):
        self._config = config
        self._session: ClientSession | None = None
        self._context: Any = None

    async def connect(self) -> None:
        cfg = self._config
        if cfg.transport == "stdio":
            server_params = StdioServerParameters(
                command=cfg.command,  # type: ignore[arg-type]
                args=cfg.args,
                env=cfg.env or None,
            )
            self._context = stdio_client(server_params)
        elif cfg.transport in ("sse", "http"):
            self._context = sse_client(url=cfg.url)  # type: ignore[arg-type]
        else:
            raise ValueError(f"Unsupported transport: {cfg.transport}")

        read, write = await self._context.__aenter__()
        self._session = ClientSession(read, write)
        await self._session.__aenter__()
        await self._session.initialize()

    async def list_tools(self) -> list[dict[str, Any]]:
        if not self._session:
            raise RuntimeError(f"MCP client '{self._config.name}' is not connected")
        result = await self._session.list_tools()
        tools = []
        for tool in result.tools:
            tools.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            })
        return tools

    async def call_tool(self, name: str, args: dict[str, Any]) -> str:
        if not self._session:
            raise RuntimeError(f"MCP client '{self._config.name}' is not connected")
        result = await self._session.call_tool(name, args)
        parts = [c.text for c in result.content if hasattr(c, "text")]
        return "\n".join(parts)

    async def disconnect(self) -> None:
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None
        if self._context:
            await self._context.__aexit__(None, None, None)
            self._context = None
