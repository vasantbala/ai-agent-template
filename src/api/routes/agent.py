from __future__ import annotations

from langchain_core.messages import AIMessage
from fastapi import APIRouter, HTTPException, Request

from agent.graph import run_agent
from agent.state import AgentState
from api.schemas import AgentRequest, AgentResponse, ToolCall
from guardrails.input import GuardrailViolation
from memory.store import Memory

router = APIRouter()


def _extract_run_summary(state: AgentState) -> str:
    ai_messages = [m for m in state.messages if isinstance(m, AIMessage)]
    if not ai_messages:
        return ""
    last = ai_messages[-1].content
    return last[:500] if isinstance(last, str) else ""


@router.post("/v1/agent/run", response_model=AgentResponse)
async def run(request: Request, body: AgentRequest) -> AgentResponse:
    app_state = request.app.state

    scrubbed_input = app_state.pii_scrubber.scrub(body.input)

    try:
        app_state.input_guardrail.validate(scrubbed_input)
    except GuardrailViolation as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    handler = app_state.tracer.callback_handler(body.session_id)

    try:
        system_prompt = app_state.prompts.get_system_prompt()
        final_state = await run_agent(
            graph=app_state.graph,
            tenant_id=body.tenant_id,
            session_id=body.session_id,
            user_input=scrubbed_input,
            system_prompt=system_prompt,
            user_id=body.user_id,
            callbacks=[handler] if handler else [],
        )
    except Exception as exc:
        app_state.tracer.flush()
        raise HTTPException(status_code=500, detail=str(exc))

    # Store memory after the run if memory is enabled
    memory_store = getattr(app_state, "memory_store", None)
    settings = app_state.settings
    if memory_store is not None and settings.memory.enabled:
        summary = _extract_run_summary(final_state)
        if summary:
            try:
                await memory_store.store(Memory(
                    text=summary,
                    tenant_id=body.tenant_id,
                    session_id=body.session_id,
                    user_id=body.user_id,
                ))
            except Exception:
                pass  # memory store failure must never break the response

    ai_messages = [m for m in final_state.messages if isinstance(m, AIMessage)]
    raw_output = ai_messages[-1].content if ai_messages else ""
    output = app_state.pii_scrubber.scrub(raw_output if isinstance(raw_output, str) else "")

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

    trace_id = str(handler.last_trace_id) if handler and getattr(handler, "last_trace_id", None) else ""
    if trace_id and getattr(app_state.settings, "cost", None) and app_state.settings.cost.enabled:
        try:
            app_state.tracer.log_score(trace_id, "cost_usd", final_state.cost_usd)
        except Exception:
            pass

    app_state.tracer.flush()

    return AgentResponse(
        session_id=body.session_id,
        tenant_id=body.tenant_id,
        output=output,
        tasks_completed=completed_tasks,
        tool_calls=tool_calls,
        cost_usd=final_state.cost_usd,
        trace_id=trace_id,
    )
