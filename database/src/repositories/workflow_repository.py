from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from src.models.workflow import WorkflowModel
from src.repositories.base import BaseRepository


class WorkflowRepository(BaseRepository[WorkflowModel]):
    async def list_by_owner(self, owner_id: uuid.UUID) -> Sequence[WorkflowModel]:
        stmt = select(self.model).where(self.model.user_id == owner_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def list_by_scope(self, scope: str) -> Sequence[WorkflowModel]:
        stmt = select(self.model).where(self.model.scope == scope)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_draft(
        self, owner_id: uuid.UUID, session_id: uuid.UUID
    ) -> WorkflowModel | None:
        stmt = select(self.model).where(
            self.model.user_id == owner_id,
            self.model.is_draft.is_(True),
            self.model.created_via_session_id == session_id,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
