from __future__ import annotations

from langchain_core.messages import AIMessage
from fastapi import APIRouter, HTTPException, Request

from agent.graph import run_agent
from api.schemas import AgentRequest, AgentResponse, ToolCall
from guardrails.input import GuardrailViolation

router = APIRouter()


@router.post("/v1/agent/run", response_model=AgentResponse)
async def run(request: Request, body: AgentRequest) -> AgentResponse:
    app_state = request.app.state

    try:
        app_state.input_guardrail.validate(body.input)
    except GuardrailViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    handler = app_state.tracer.callback_handler(body.session_id)

    try:
        system_prompt = app_state.prompts.get_system_prompt()
        final_state = await run_agent(
            graph=app_state.graph,
            tenant_id=body.tenant_id,
            session_id=body.session_id,
            user_input=body.input,
            system_prompt=system_prompt,
            callbacks=[handler],
        )
    except Exception as exc:
        app_state.tracer.flush()
        raise HTTPException(status_code=500, detail=str(exc))

    ai_messages = [m for m in final_state.messages if isinstance(m, AIMessage)]
    output = ai_messages[-1].content if ai_messages else ""

    completed_tasks = [t for t in final_state.tasks if t.status == "completed"]
    tool_calls = [
        ToolCall(
            tool_name=t.tool_name or "",
            args=t.tool_args,
            result=t.result or "",
            success=t.status == "completed",
        )
        for t in final_state.tasks
        if t.tool_name
    ]

    app_state.tracer.flush()

    return AgentResponse(
        session_id=body.session_id,
        tenant_id=body.tenant_id,
        output=output,
        tasks_completed=completed_tasks,
        tool_calls=tool_calls,
        trace_id=str(handler.last_trace_id) if getattr(handler, "last_trace_id", None) else "",
    )
