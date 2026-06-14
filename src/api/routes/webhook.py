from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel

from agent.graph import run_agent

router = APIRouter()


class WebhookRequest(BaseModel):
    tenant_id: str
    input: str
    session_id: str | None = None
    user_id: str | None = None


class WebhookResponse(BaseModel):
    accepted: bool
    session_id: str


@router.post("/v1/triggers/webhook", response_model=WebhookResponse, status_code=202)
async def webhook(
    request: Request,
    body: WebhookRequest,
    background_tasks: BackgroundTasks,
) -> WebhookResponse:
    app_state = request.app.state
    session_id = body.session_id or f"wh-{uuid.uuid4().hex[:8]}"

    async def _run() -> None:
        system_prompt = app_state.prompts.get_system_prompt()
        await run_agent(
            graph=app_state.graph,
            tenant_id=body.tenant_id,
            session_id=session_id,
            user_input=body.input,
            system_prompt=system_prompt,
            user_id=body.user_id,
        )

    background_tasks.add_task(_run)
    return WebhookResponse(accepted=True, session_id=session_id)
