from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.entities.oauth_connection import OAuthConnection
from auth.domain.ports.oauth_connection_repository import OAuthConnectionRepository

from ..mappers.oauth_connection_mapper import OAuthConnectionMapper
from ..orm.oauth_connection_model import OAuthConnectionModel


class PgOAuthRepository(OAuthConnectionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: UUID, service: str, tokens: dict[str, Any]) -> OAuthConnection:
        model = OAuthConnectionModel(
            oauth_id=uuid4(),
            user_id=user_id,
            service=service,
            credential_id=tokens["credential_id"],
            access_token_encrypted=tokens["access_token_encrypted"],
            refresh_token_encrypted=tokens.get("refresh_token_encrypted"),
            scopes=tokens.get("scopes", []),
            account_id=tokens.get("account_id"),
            display_name=tokens.get("display_name"),
            is_active=True,
            connected_at=datetime.now(timezone.utc),
        )
        self._session.add(model)
        await self._session.flush()
        return OAuthConnectionMapper.to_domain(model)

    async def get_by_credential_id(self, credential_id: UUID) -> OAuthConnection | None:
        stmt = select(OAuthConnectionModel).where(OAuthConnectionModel.credential_id == credential_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return OAuthConnectionMapper.to_domain(model)

    async def get_active_for_user(self, user_id: UUID, service: str) -> OAuthConnection | None:
        stmt = select(OAuthConnectionModel).where(
            OAuthConnectionModel.user_id == user_id,
            OAuthConnectionModel.service == service,
            OAuthConnectionModel.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return OAuthConnectionMapper.to_domain(model)

    async def list_for_user(self, user_id: UUID) -> list[OAuthConnection]:
        stmt = select(OAuthConnectionModel).where(
            OAuthConnectionModel.user_id == user_id,
            OAuthConnectionModel.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return [OAuthConnectionMapper.to_domain(model) for model in result.scalars().all()]

    async def update_tokens(self, credential_id: UUID, new_tokens: dict[str, Any]) -> None:
        values: dict[str, Any] = {"last_refreshed_at": datetime.now(timezone.utc)}
        if "access_token_encrypted" in new_tokens:
            values["access_token_encrypted"] = new_tokens["access_token_encrypted"]
        if "refresh_token_encrypted" in new_tokens:
            values["refresh_token_encrypted"] = new_tokens["refresh_token_encrypted"]
        stmt = (
            update(OAuthConnectionModel)
            .where(OAuthConnectionModel.credential_id == credential_id)
            .values(**values)
        )
        await self._session.execute(stmt)

    async def revoke(self, credential_id: UUID) -> None:
        stmt = (
            update(OAuthConnectionModel)
            .where(OAuthConnectionModel.credential_id == credential_id)
            .values(is_active=False)
        )
        await self._session.execute(stmt)
