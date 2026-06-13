import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.state import AgentState, Task
from agent.nodes.reason import reason
from agent.nodes.execute import execute
from agent.graph import _should_execute, build_graph
from config.settings import AgentConfig, LLMSettings
from llm.client import LLMClient
from tools.registry import MCPRegistry
from config.prompts import PromptManager


def make_llm_settings() -> LLMSettings:
    return LLMSettings(provider="anthropic", model="claude-sonnet-4-6", api_key="sk-test")


def make_agent_config(**overrides) -> AgentConfig:
    return AgentConfig(**{"max_iterations": 5, **overrides})


def make_state(**overrides) -> AgentState:
    defaults = {
        "tenant_id": "test",
        "session_id": "sess-1",
        "messages": [HumanMessage(content="Hello")],
    }
    return AgentState(**(defaults | overrides))


def mock_llm_response(content: str = "Done", tool_calls: list | None = None) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = tool_calls or []
    response = MagicMock()
    response.choices = [choice]
    return response


class TestShouldExecute:
    def test_returns_end_when_no_tasks(self):
        state = make_state(tasks=[], current_task_index=0)
        assert _should_execute(state) == "end"

    def test_returns_execute_when_tasks_remain(self):
        state = make_state(
            tasks=[Task(description="do something", tool_name="search", tool_args={})],
            current_task_index=0,
        )
        assert _should_execute(state) == "execute"

    def test_returns_end_when_all_tasks_processed(self):
        task = Task(description="done", tool_name="search", tool_args={}, status="completed")
        state = make_state(tasks=[task], current_task_index=1)
        assert _should_execute(state) == "end"

    def test_returns_end_on_error(self):
        state = make_state(error="Something went wrong")
        assert _should_execute(state) == "end"


class TestReasonNode:
    async def test_increments_iteration(self):
        llm = AsyncMock(spec=LLMClient)
        llm.complete.return_value = mock_llm_response("Hello")
        state = make_state(iteration=2)
        result = await reason(state, llm, [], max_iterations=10)
        assert result["iteration"] == 3

    async def test_returns_error_at_max_iterations(self):
        llm = AsyncMock(spec=LLMClient)
        state = make_state(iteration=5)
        result = await reason(state, llm, [], max_iterations=5)
        assert "error" in result
        assert "Max iterations" in result["error"]

    async def test_creates_tasks_from_tool_calls(self):
        llm = AsyncMock(spec=LLMClient)
        tc = MagicMock()
        tc.function.name = "search"
        tc.function.arguments = '{"query": "python"}'
        llm.complete.return_value = mock_llm_response(tool_calls=[tc])

        state = make_state()
        result = await reason(state, llm, [{"type": "function", "function": {"name": "search"}}], max_iterations=10)

        assert len(result["tasks"]) == 1
        assert result["tasks"][0].tool_name == "search"
        assert result["tasks"][0].tool_args == {"query": "python"}

    async def test_no_tasks_when_no_tool_calls(self):
        llm = AsyncMock(spec=LLMClient)
        llm.complete.return_value = mock_llm_response("Final answer")
        state = make_state()
        result = await reason(state, llm, [], max_iterations=10)
        assert "tasks" not in result or result.get("tasks") == []


class TestExecuteNode:
    async def test_calls_registry_with_correct_args(self):
        registry = AsyncMock(spec=MCPRegistry)
        registry.call_tool.return_value = "search result"

        task = Task(description="search", tool_name="search", tool_args={"query": "python"})
        state = make_state(tasks=[task], current_task_index=0)

        await execute(state, registry)
        registry.call_tool.assert_awaited_once_with("search", {"query": "python"})

    async def test_marks_task_completed_on_success(self):
        registry = AsyncMock(spec=MCPRegistry)
        registry.call_tool.return_value = "result"

        task = Task(description="search", tool_name="search", tool_args={})
        state = make_state(tasks=[task], current_task_index=0)

        result = await execute(state, registry)
        assert result["tasks"][0].status == "completed"
        assert result["tasks"][0].result == "result"

    async def test_marks_task_failed_on_error(self):
        registry = AsyncMock(spec=MCPRegistry)
        registry.call_tool.side_effect = Exception("tool error")

        task = Task(description="search", tool_name="search", tool_args={})
        state = make_state(tasks=[task], current_task_index=0)

        result = await execute(state, registry)
        assert result["tasks"][0].status == "failed"
        assert "tool error" in result["tasks"][0].result

    async def test_advances_task_index(self):
        registry = AsyncMock(spec=MCPRegistry)
        registry.call_tool.return_value = "ok"

        task = Task(description="search", tool_name="search", tool_args={})
        state = make_state(tasks=[task], current_task_index=0)

        result = await execute(state, registry)
        assert result["current_task_index"] == 1

    async def test_adds_tool_message_to_messages(self):
        registry = AsyncMock(spec=MCPRegistry)
        registry.call_tool.return_value = "tool output"

        task = Task(description="search", tool_name="search", tool_args={})
        state = make_state(tasks=[task], current_task_index=0)

        result = await execute(state, registry)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], ToolMessage)
        assert result["messages"][0].content == "tool output"


class TestBuildGraph:
    def test_graph_compiles(self):
        llm = MagicMock(spec=LLMClient)
        registry = MagicMock(spec=MCPRegistry)
        prompts = MagicMock(spec=PromptManager)
        config = make_agent_config()

        graph = build_graph(llm, registry, prompts, config)
        assert graph is not None
