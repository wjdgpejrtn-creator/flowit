from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from src.models.node_definition import NodeDefinitionModel
from src.repositories.base import BaseRepository


class NodeDefinitionRepository(BaseRepository[NodeDefinitionModel]):
    async def search_by_embedding(
        self, query_vec: list[float], top_k: int = 10
    ) -> Sequence[NodeDefinitionModel]:
        stmt = (
            select(self.model)
            .where(self.model.is_active.is_(True))
            .order_by(self.model.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def upsert(self, **kwargs) -> NodeDefinitionModel:
        node_type = kwargs.get("node_type")
        stmt = select(self.model).where(self.model.node_type == node_type)
        result = await self.session.execute(stmt)
        existing = result.scalars().first()

        if existing:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            await self.session.flush()
            await self.session.refresh(existing)
            return existing
        return await self.create(**kwargs)

    async def reembed(self, node_id: uuid.UUID, embedding: list[float]) -> None:
        instance = await self.get_or_raise(node_id)
        instance.embedding = embedding
        await self.session.flush()
