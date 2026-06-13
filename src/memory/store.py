from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from config.settings import MemoryConfig
from memory.embedding import EmbeddingClient


class Memory(BaseModel):
    text: str
    tenant_id: str
    session_id: str
    user_id: str | None = None
    created_at: str = ""

    def model_post_init(self, __context: object) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, config: MemoryConfig, embedder: EmbeddingClient) -> None:
        self._config = config
        self._embedder = embedder
        self._client = AsyncQdrantClient(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key,
        )

    async def ensure_collection(self, dimensions: int = 1536) -> None:
        collections = await self._client.get_collections()
        names = {c.name for c in collections.collections}
        if self._config.collection_name not in names:
            await self._client.create_collection(
                collection_name=self._config.collection_name,
                vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
            )

    async def store(self, memory: Memory) -> None:
        vector = await self._embedder.embed(memory.text)
        await self._client.upsert(
            collection_name=self._config.collection_name,
            points=[
                PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload={
                        "text": memory.text,
                        "tenant_id": memory.tenant_id,
                        "session_id": memory.session_id,
                        "user_id": memory.user_id,
                        "created_at": memory.created_at,
                    },
                )
            ],
        )

    async def retrieve(
        self,
        query: str,
        tenant_id: str,
        scope: Literal["session", "user", "tenant", "global"],
        session_id: str | None = None,
        user_id: str | None = None,
        top_k: int = 5,
    ) -> list[str]:
        vector = await self._embedder.embed(query)
        query_filter = _build_filter(scope, tenant_id, session_id, user_id)

        results = await self._client.search(
            collection_name=self._config.collection_name,
            query_vector=vector,
            query_filter=query_filter,
            limit=top_k,
        )
        return [r.payload["text"] for r in results if r.payload]


def _build_filter(
    scope: str,
    tenant_id: str,
    session_id: str | None,
    user_id: str | None,
) -> Filter | None:
    conditions: list[FieldCondition] = []

    if scope in ("session", "user", "tenant"):
        conditions.append(FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)))

    if scope == "session" and session_id:
        conditions.append(FieldCondition(key="session_id", match=MatchValue(value=session_id)))

    if scope == "user" and user_id:
        conditions.append(FieldCondition(key="user_id", match=MatchValue(value=user_id)))

    return Filter(must=conditions) if conditions else None
