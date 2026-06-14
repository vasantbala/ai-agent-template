from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from memory.store import Memory

router = APIRouter()


class SeedRequest(BaseModel):
    tenant_id: str
    documents: list[str]
    session_id: str = "seed"
    user_id: str | None = None


class SeedResponse(BaseModel):
    seeded: int


@router.post("/v1/kb/seed", response_model=SeedResponse)
async def seed_kb(request: Request, body: SeedRequest) -> SeedResponse:
    app_state = request.app.state
    memory_store = getattr(app_state, "memory_store", None)

    if memory_store is None or not app_state.settings.memory.enabled:
        raise HTTPException(
            status_code=400,
            detail="Memory is not enabled. Set MEMORY__ENABLED=true to use the KB seeder.",
        )

    documents = [d.strip() for d in body.documents if d.strip()]
    if not documents:
        return SeedResponse(seeded=0)

    for doc in documents:
        await memory_store.store(Memory(
            text=doc,
            tenant_id=body.tenant_id,
            session_id=body.session_id,
            user_id=body.user_id,
        ))

    return SeedResponse(seeded=len(documents))
