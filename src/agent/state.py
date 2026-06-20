from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_call_id: str | None = None  # LLM's original tool call id for ToolMessage
    description: str
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    tool_name: str | None = None
    tool_args: dict[str, Any] = {}
    result: str | None = None


class AgentState(BaseModel):
    tenant_id: str
    session_id: str
    user_id: str | None = None
    messages: Annotated[list[BaseMessage], add_messages] = []
    tasks: list[Task] = []
    current_task_index: int = 0
    iteration: int = 0
    tokens_used: int = 0
    cost_usd: float = 0.0
    error: str | None = None
