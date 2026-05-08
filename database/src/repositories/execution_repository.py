from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select, update

from src.models.execution import ExecutionModel
from src.repositories.base import BaseRepository


class ExecutionRepository(BaseRepository[ExecutionModel]):
    async def update_status(self, execution_id: uuid.UUID, status: str) -> None:
        stmt = (
            update(self.model)
            .where(self.model.execution_id == execution_id)
            .values(status=status)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def list_by_workflow(
        self, workflow_id: uuid.UUID
    ) -> Sequence[ExecutionModel]:
        stmt = (
            select(self.model)
            .where(self.model.workflow_id == workflow_id)
            .order_by(self.model.started_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
