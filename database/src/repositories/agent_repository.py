from __future__ import annotations

import uuid

from sqlalchemy import func, update

from src.models.agent import AgentModel
from src.repositories.base import BaseRepository


class AgentRepository(BaseRepository[AgentModel]):
    async def register(self, **kwargs) -> AgentModel:
        return await self.create(**kwargs)

    async def heartbeat(self, agent_id: uuid.UUID) -> None:
        stmt = (
            update(self.model)
            .where(self.model.agent_id == agent_id)
            .values(last_heartbeat=func.now(), status="active")
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_public_key(self, agent_id: uuid.UUID) -> str | None:
        instance = await self.get(agent_id)
        return instance.public_key if instance else None
