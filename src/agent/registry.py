from __future__ import annotations

from config.settings import SubAgentConfig
from agent.subagent import SubAgentClient

_TOOL_PREFIX = "call_"


class AgentRegistry:
    def __init__(self, configs: list[SubAgentConfig]) -> None:
        self._clients: dict[str, SubAgentClient] = {
            cfg.name: SubAgentClient(cfg) for cfg in configs
        }
        self._descriptions: dict[str, str] = {
            cfg.name: cfg.description for cfg in configs
        }

    def tool_schemas(self) -> list[dict]:
        return [
            {
                "name": f"{_TOOL_PREFIX}{name}",
                "description": description,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "The task or question to delegate to this agent.",
                        }
                    },
                    "required": ["task"],
                },
            }
            for name, description in self._descriptions.items()
        ]

    def get(self, tool_name: str) -> SubAgentClient | None:
        if not tool_name.startswith(_TOOL_PREFIX):
            return None
        name = tool_name[len(_TOOL_PREFIX):]
        return self._clients.get(name)

    def is_sub_agent_tool(self, tool_name: str) -> bool:
        return self.get(tool_name) is not None
