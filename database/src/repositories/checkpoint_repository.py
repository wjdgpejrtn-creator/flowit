from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.checkpoint import CheckpointModel


class CheckpointRepository:
    """Delegates to LangGraph PostgresSaver; thin wrapper for direct queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest(
        self, thread_id: str, checkpoint_ns: str = ""
    ) -> CheckpointModel | None:
        stmt = (
            select(CheckpointModel)
            .where(
                CheckpointModel.thread_id == thread_id,
                CheckpointModel.checkpoint_ns == checkpoint_ns,
            )
            .order_by(CheckpointModel.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
