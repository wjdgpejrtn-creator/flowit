from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_agent.domain.entities.memory_entry import MemoryEntry
from ai_agent.domain.ports.agent_memory_repository import AgentMemoryRepository

from ..mappers.agent_memory_mapper import AgentMemoryMapper
from ..orm.agent_memory_model import AgentMemoryModel


class PgAgentMemoryRepository(AgentMemoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, entry: MemoryEntry) -> None:
        model = AgentMemoryMapper.to_orm(entry)
        self._session.add(model)
        await self._session.flush()

    async def find_by_user(self, user_id: UUID, limit: int = 20) -> list[MemoryEntry]:
        stmt = (
            select(AgentMemoryModel)
            .where(AgentMemoryModel.user_id == user_id)
            .order_by(AgentMemoryModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [AgentMemoryMapper.to_domain(row) for row in result.scalars().all()]

    async def find_by_session(self, session_id: UUID, limit: int = 20) -> list[MemoryEntry]:
        stmt = (
            select(AgentMemoryModel)
            .where(AgentMemoryModel.source_session_id == session_id)
            .order_by(AgentMemoryModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [AgentMemoryMapper.to_domain(row) for row in result.scalars().all()]
