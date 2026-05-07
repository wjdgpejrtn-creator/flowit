from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.entities.session import Session
from auth.domain.ports.session_repository import SessionRepository

from ..mappers.session_mapper import SessionMapper
from ..orm.session_model import SessionModel


class PgSessionRepository(SessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: UUID,
        session_hash: str,
        expires_at: datetime | None = None,
        device_info: str | None = None,
        **kwargs: object,
    ) -> Session:
        model = SessionModel(
            session_id=uuid4(),
            user_id=user_id,
            session_hash=session_hash,
            expires_at=expires_at,
            is_revoked=False,
            created_at=datetime.now(timezone.utc),
            device_info=device_info,
        )
        self._session.add(model)
        await self._session.flush()
        return SessionMapper.to_domain(model)

    async def find_by_hash(self, session_hash: str) -> Optional[Session]:
        stmt = select(SessionModel).where(SessionModel.session_hash == session_hash)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return SessionMapper.to_domain(model)

    async def revoke(self, session_id: UUID) -> None:
        stmt = update(SessionModel).where(SessionModel.session_id == session_id).values(is_revoked=True)
        await self._session.execute(stmt)

    async def revoke_all_for_user(self, user_id: UUID) -> int:
        stmt = (
            update(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.is_revoked.is_(False))
            .values(is_revoked=True)
        )
        result = await self._session.execute(stmt)
        return result.rowcount
