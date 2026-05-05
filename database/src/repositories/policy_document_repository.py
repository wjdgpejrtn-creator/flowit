from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from src.models.document import DocumentBlockModel
from src.repositories.base import BaseRepository


class PolicyDocumentRepository(BaseRepository[DocumentBlockModel]):
    async def upsert(self, **kwargs) -> DocumentBlockModel:
        block_id = kwargs.get("id")
        if block_id:
            existing = await self.get(block_id)
            if existing:
                for key, value in kwargs.items():
                    if key != "id":
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
    ) -> Sequence[DocumentBlockModel]:
        stmt = select(self.model)
        if document_id:
            stmt = stmt.where(self.model.document_id == document_id)
        stmt = (
            stmt.order_by(self.model.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
