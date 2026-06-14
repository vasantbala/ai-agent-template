from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from agent.state import Task


class AgentRequest(BaseModel):
    tenant_id: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str | None = None
    input: str
    context: dict[str, Any] = {}


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ToolCall(BaseModel):
    tool_name: str
    args: dict[str, Any]
    result: str
    success: bool


class AgentResponse(BaseModel):
    session_id: str
    tenant_id: str
    output: str
    tasks_completed: list[Task] = []
    tool_calls: list[ToolCall] = []
    tokens_used: TokenUsage = TokenUsage()
    cost_usd: float = 0.0
    trace_id: str = ""


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
