from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from src.models.chat import ChatMessageModel
from src.repositories.base import BaseRepository


class ChatRepository(BaseRepository[ChatMessageModel]):
    async def append_message(
        self,
        session_id: uuid.UUID,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> ChatMessageModel:
        return await self.create(
            session_id=session_id,
            role=role,
            content=content,
            metadata=metadata or {},
        )

    async def load_messages(
        self, session_id: uuid.UUID, limit: int = 50
    ) -> Sequence[ChatMessageModel]:
        stmt = (
            select(self.model)
            .where(self.model.session_id == session_id)
            .order_by(self.model.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
