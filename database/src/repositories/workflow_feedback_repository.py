from __future__ import annotations

import uuid
from typing import Any, Sequence

from sqlalchemy import func, select

from src.models.workflow_feedback import WorkflowFeedbackModel
from src.repositories.base import BaseRepository


class WorkflowFeedbackRepository(BaseRepository[WorkflowFeedbackModel]):
    async def list_by_workflow(
        self, workflow_id: uuid.UUID
    ) -> Sequence[WorkflowFeedbackModel]:
        stmt = (
            select(self.model)
            .where(self.model.workflow_id == workflow_id)
            .order_by(self.model.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def aggregate(self, workflow_id: uuid.UUID) -> dict[str, Any]:
        stmt = select(
            func.count().label("total"),
            func.avg(self.model.rating).label("avg_rating"),
        ).where(self.model.workflow_id == workflow_id)
        result = await self.session.execute(stmt)
        row = result.one()
        return {"total": row.total, "avg_rating": float(row.avg_rating or 0)}
