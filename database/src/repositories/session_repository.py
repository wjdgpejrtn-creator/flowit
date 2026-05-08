from __future__ import annotations

import uuid

from sqlalchemy import select, update

from src.models.chat import SessionModel
from src.repositories.base import BaseRepository


class SessionRepository(BaseRepository[SessionModel]):
    """H-3 contract: implements REQ-002 session ABC signatures."""

    async def create_session(
        self, user_id: uuid.UUID, session_hash: str, **kwargs
    ) -> SessionModel:
        return await self.create(
            user_id=user_id, session_hash=session_hash, **kwargs
        )

    async def find_by_hash(self, session_hash: str) -> SessionModel | None:
        stmt = select(self.model).where(
            self.model.session_hash == session_hash,
            self.model.is_revoked.is_(False),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def revoke(self, session_id: uuid.UUID) -> None:
        stmt = (
            update(self.model)
            .where(self.model.session_id == session_id)
            .values(is_revoked=True)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        stmt = (
            update(self.model)
            .where(
                self.model.user_id == user_id,
                self.model.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
