import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from agent.state import AgentState, Task
from agent.nodes.reason import reason
from agent.nodes.execute import execute
from agent.graph import _should_execute, build_graph
from config.settings import AgentConfig, LLMSettings, ReliabilityConfig
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


def mock_llm_response(
    content: str = "Done",
    tool_calls: list | None = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
) -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.message.tool_calls = tool_calls or []
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
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

    def test_graph_compiles_with_checkpointer(self):
        from langgraph.checkpoint.memory import InMemorySaver
        llm = MagicMock(spec=LLMClient)
        registry = MagicMock(spec=MCPRegistry)
        prompts = MagicMock(spec=PromptManager)
        config = make_agent_config()

        graph = build_graph(llm, registry, prompts, config, checkpointer=InMemorySaver())
        assert graph is not None

    async def test_run_agent_uses_session_id_as_thread_id(self):
        from agent.graph import run_agent

        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "tenant_id": "t1",
            "session_id": "sess-42",
            "messages": [],
            "tasks": [],
            "current_task_index": 0,
            "iteration": 1,
            "tokens_used": 0,
            "error": None,
        }

        await run_agent(mock_graph, "t1", "sess-42", "hello", "sys prompt")

        call_config = mock_graph.ainvoke.call_args[1]["config"]
        assert call_config["configurable"]["thread_id"] == "sess-42"

    async def test_run_agent_includes_callbacks_in_config(self):
        from agent.graph import run_agent

        mock_graph = AsyncMock()
        mock_graph.ainvoke.return_value = {
            "tenant_id": "t1",
            "session_id": "s1",
            "messages": [],
            "tasks": [],
            "current_task_index": 0,
            "iteration": 1,
            "tokens_used": 0,
            "error": None,
        }
        cb = MagicMock()

        await run_agent(mock_graph, "t1", "s1", "hello", "sys", callbacks=[cb])

        call_config = mock_graph.ainvoke.call_args[1]["config"]
        assert cb in call_config["callbacks"]

    def test_graph_compiles_with_hitl_enabled(self):
        llm = MagicMock(spec=LLMClient)
        registry = MagicMock(spec=MCPRegistry)
        prompts = MagicMock(spec=PromptManager)
        config = make_agent_config()
        rel = ReliabilityConfig(hitl_enabled=True)

        graph = build_graph(llm, registry, prompts, config, reliability=rel)
        assert graph is not None

    def test_graph_compiles_without_hitl(self):
        llm = MagicMock(spec=LLMClient)
        registry = MagicMock(spec=MCPRegistry)
        prompts = MagicMock(spec=PromptManager)
        config = make_agent_config()
        rel = ReliabilityConfig(hitl_enabled=False)

        graph = build_graph(llm, registry, prompts, config, reliability=rel)
        assert graph is not None


class TestReasonNodeWiring:
    async def test_accumulates_token_usage(self):
        llm = AsyncMock(spec=LLMClient)
        llm.complete.return_value = mock_llm_response("Done", prompt_tokens=100, completion_tokens=50)
        state = make_state(tokens_used=200)

        result = await reason(state, llm, [], max_iterations=10)

        assert result["tokens_used"] == 350  # 200 + 100 + 50

    async def test_returns_error_when_budget_exceeded(self):
        llm = AsyncMock(spec=LLMClient)
        llm.complete.return_value = mock_llm_response("Done", prompt_tokens=100, completion_tokens=50)
        state = make_state(tokens_used=0)

        result = await reason(state, llm, [], max_iterations=10, max_tokens=100)

        assert "error" in result
        assert "Token budget exceeded" in result["error"]
        assert result["tokens_used"] == 150

    async def test_no_budget_limit_when_max_tokens_zero(self):
        llm = AsyncMock(spec=LLMClient)
        llm.complete.return_value = mock_llm_response("Done", prompt_tokens=1000, completion_tokens=1000)
        state = make_state(tokens_used=0)

        result = await reason(state, llm, [], max_iterations=10, max_tokens=0)

        assert "error" not in result or result.get("error") is None
        assert result["tokens_used"] == 2000

    async def test_calls_context_manager_when_provided(self):
        from unittest.mock import AsyncMock as AM
        llm = AsyncMock(spec=LLMClient)
        llm.complete.return_value = mock_llm_response("Done")

        ctx_mgr = MagicMock()
        ctx_mgr.maybe_summarise = AM(return_value=[HumanMessage(content="Hello")])

        state = make_state()
        await reason(state, llm, [], max_iterations=10, context_mgr=ctx_mgr)

        ctx_mgr.maybe_summarise.assert_awaited_once_with(state.messages)

    async def test_skips_context_manager_when_none(self):
        llm = AsyncMock(spec=LLMClient)
        llm.complete.return_value = mock_llm_response("Done")
        state = make_state()

        # Should not raise even without context_mgr
        result = await reason(state, llm, [], max_iterations=10, context_mgr=None)
        assert "error" not in result or result.get("error") is None
