from __future__ import annotations

import pytest

from config.settings import SubAgentConfig
from agent.registry import AgentRegistry
from agent.subagent import SubAgentClient


def make_config(name: str, url: str = "http://localhost:8002", description: str = "A test agent") -> SubAgentConfig:
    return SubAgentConfig(name=name, url=url, description=description)


class TestAgentRegistry:
    def test_empty_configs_produces_empty_schemas(self):
        reg = AgentRegistry([])
        assert reg.tool_schemas() == []

    def test_schema_name_prefixed_with_call(self):
        reg = AgentRegistry([make_config("researcher")])
        schemas = reg.tool_schemas()
        assert schemas[0]["name"] == "call_researcher"

    def test_schema_description_matches_config(self):
        reg = AgentRegistry([make_config("worker", description="Processes data")])
        assert reg.tool_schemas()[0]["description"] == "Processes data"

    def test_schema_has_task_input_property(self):
        reg = AgentRegistry([make_config("worker")])
        schema = reg.tool_schemas()[0]
        assert "task" in schema["input_schema"]["properties"]
        assert schema["input_schema"]["required"] == ["task"]

    def test_multiple_configs_produce_multiple_schemas(self):
        reg = AgentRegistry([make_config("a"), make_config("b"), make_config("c")])
        assert len(reg.tool_schemas()) == 3

    def test_get_returns_client_for_known_tool(self):
        reg = AgentRegistry([make_config("researcher")])
        client = reg.get("call_researcher")
        assert isinstance(client, SubAgentClient)

    def test_get_returns_none_for_unknown_tool(self):
        reg = AgentRegistry([make_config("researcher")])
        assert reg.get("call_unknown") is None

    def test_get_returns_none_without_prefix(self):
        reg = AgentRegistry([make_config("researcher")])
        assert reg.get("researcher") is None

    def test_is_sub_agent_tool_true_for_known(self):
        reg = AgentRegistry([make_config("worker")])
        assert reg.is_sub_agent_tool("call_worker") is True

    def test_is_sub_agent_tool_false_for_unknown(self):
        reg = AgentRegistry([make_config("worker")])
        assert reg.is_sub_agent_tool("call_unknown") is False

    def test_is_sub_agent_tool_false_for_mcp_tool(self):
        reg = AgentRegistry([make_config("worker")])
        assert reg.is_sub_agent_tool("read_file") is False

    def test_empty_registry_is_sub_agent_tool_always_false(self):
        reg = AgentRegistry([])
        assert reg.is_sub_agent_tool("call_anything") is False
