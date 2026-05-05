from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chat import ChatSessionModel


class SessionManager:
    """Dual-layer session management (Redis + PostgreSQL).

    Redis is the hot cache; PostgreSQL is the persistent store.
    On this PC Redis is unavailable, so this implementation is PG-only.
    Redis integration will be added when REQ-002 provides the Redis client.
    """

    def __init__(
        self,
        session: AsyncSession,
        ttl_idle: int = 1800,
        ttl_max: int = 86400,
        max_sessions_per_user: int = 25,
    ) -> None:
        self._session = session
        self._ttl_idle = ttl_idle
        self._ttl_max = ttl_max
        self._max_sessions = max_sessions_per_user

    async def create_session(
        self,
        user_id: uuid.UUID,
        kind: str = "chat",
        session_hash: str | None = None,
    ) -> ChatSessionModel:
        await self._evict_oldest(user_id)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self._ttl_max)
        hash_value = session_hash or uuid.uuid4().hex

        instance = ChatSessionModel(
            user_id=user_id,
            session_hash=hash_value,
            kind=kind,
            expires_at=expires_at,
        )
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def resume_or_create(
        self, user_id: uuid.UUID, session_hash: str | None = None
    ) -> ChatSessionModel:
        if session_hash:
            stmt = select(ChatSessionModel).where(
                ChatSessionModel.session_hash == session_hash,
                ChatSessionModel.is_revoked.is_(False),
            )
            result = await self._session.execute(stmt)
            existing = result.scalars().first()
            if existing and existing.expires_at > datetime.now(timezone.utc):
                existing.last_activity_at = datetime.now(timezone.utc)
                await self._session.flush()
                return existing
        return await self.create_session(user_id)

    async def _evict_oldest(self, user_id: uuid.UUID) -> None:
        stmt = (
            select(ChatSessionModel)
            .where(
                ChatSessionModel.user_id == user_id,
                ChatSessionModel.is_revoked.is_(False),
            )
            .order_by(ChatSessionModel.last_activity_at.desc())
        )
        result = await self._session.execute(stmt)
        sessions = result.scalars().all()

        if len(sessions) >= self._max_sessions:
            to_revoke = sessions[self._max_sessions - 1 :]
            ids = [s.id for s in to_revoke]
            revoke_stmt = (
                update(ChatSessionModel)
                .where(ChatSessionModel.id.in_(ids))
                .values(is_revoked=True)
            )
            await self._session.execute(revoke_stmt)
            await self._session.flush()
