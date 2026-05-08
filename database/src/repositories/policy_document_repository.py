from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from src.models.document import DocumentChunkModel
from src.repositories.base import BaseRepository


class PolicyDocumentRepository(BaseRepository[DocumentChunkModel]):
    async def upsert(self, **kwargs) -> DocumentChunkModel:
        chunk_id = kwargs.get("chunk_id")
        if chunk_id:
            existing = await self.get(chunk_id)
            if existing:
                for key, value in kwargs.items():
                    if key != "chunk_id":
                        setattr(existing, key, value)
                await self.session.flush()
                await self.session.refresh(existing)
                return existing
        return await self.create(**kwargs)

    async def search_by_embedding(
        self,
        query_vec: list[float],
        document_id: uuid.UUID | None = None,
        top_k: int = 10,
    ) -> Sequence[DocumentChunkModel]:
        stmt = select(self.model)
        if document_id:
            stmt = stmt.where(self.model.parent_document_id == document_id)
        stmt = (
            stmt.order_by(self.model.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
