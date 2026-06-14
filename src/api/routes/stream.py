from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk

from api.schemas import AgentRequest
from guardrails.input import GuardrailViolation

router = APIRouter()


async def _token_stream(graph, initial_state, config):
    output_tokens: list[str] = []
    async for event in graph.astream_events(initial_state, config=config, version="v2"):
        if event["event"] == "on_chat_model_stream":
            chunk: AIMessageChunk = event["data"]["chunk"]
            if chunk.content and isinstance(chunk.content, str):
                output_tokens.append(chunk.content)
                yield f'data: {json.dumps({"type": "token", "content": chunk.content})}\n\n'
    full_output = "".join(output_tokens)
    yield f'data: {json.dumps({"type": "done", "output": full_output})}\n\n'
    yield "data: [DONE]\n\n"


@router.post("/v1/agent/stream")
async def stream(request: Request, body: AgentRequest) -> StreamingResponse:
    from langchain_core.messages import HumanMessage, SystemMessage

    from agent.state import AgentState

    app_state = request.app.state

    scrubbed_input = app_state.pii_scrubber.scrub(body.input)

    try:
        app_state.input_guardrail.validate(scrubbed_input)
    except GuardrailViolation as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))

    system_prompt = app_state.prompts.get_system_prompt()
    initial_state = AgentState(
        tenant_id=body.tenant_id,
        session_id=body.session_id,
        user_id=body.user_id,
        messages=[
            SystemMessage(content=system_prompt),
            HumanMessage(content=scrubbed_input),
        ],
    )
    config = {"configurable": {"thread_id": body.session_id}}

    return StreamingResponse(
        _token_stream(app_state.graph, initial_state, config),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
