from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from toolset.domain.entities.tool_execution_record import ToolExecutionRecord
from toolset.domain.ports.tool_execution_repository import ToolExecutionRepository

from ..mappers.tool_execution_mapper import ToolExecutionMapper
from ..orm.tool_execution_model import ToolExecutionModel


class PgToolExecutionRepository(ToolExecutionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, record: ToolExecutionRecord) -> None:
        model = ToolExecutionMapper.to_orm(record)
        self._session.add(model)
        await self._session.flush()

    async def find_by_tool(self, tool_name: str, limit: int = 100) -> list[ToolExecutionRecord]:
        stmt = (
            select(ToolExecutionModel)
            .where(ToolExecutionModel.tool_name == tool_name)
            .order_by(ToolExecutionModel.executed_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [ToolExecutionMapper.to_domain(row) for row in result.scalars().all()]
