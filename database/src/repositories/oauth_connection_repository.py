from __future__ import annotations

import uuid

from sqlalchemy import select, update

from src.models.oauth_connection import OAuthConnectionModel
from src.repositories.base import BaseRepository


class OAuthConnectionRepository(BaseRepository[OAuthConnectionModel]):
    """H-3 contract: implements REQ-002 OAuth ABC signatures."""

    async def get_by_credential_id(
        self, credential_id: uuid.UUID
    ) -> OAuthConnectionModel | None:
        stmt = select(self.model).where(self.model.credential_id == credential_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_active_for_user(
        self, user_id: uuid.UUID, service: str
    ) -> OAuthConnectionModel | None:
        stmt = select(self.model).where(
            self.model.user_id == user_id,
            self.model.service == service,
            self.model.is_active.is_(True),
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update_tokens(
        self,
        connection_id: uuid.UUID,
        access_token_encrypted: bytes,
        refresh_token_encrypted: bytes | None = None,
    ) -> None:
        values: dict = {"access_token_encrypted": access_token_encrypted}
        if refresh_token_encrypted is not None:
            values["refresh_token_encrypted"] = refresh_token_encrypted
        stmt = (
            update(self.model)
            .where(self.model.oauth_id == connection_id)
            .values(**values)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def revoke(self, connection_id: uuid.UUID) -> None:
        stmt = (
            update(self.model)
            .where(self.model.oauth_id == connection_id)
            .values(is_active=False)
        )
        await self.session.execute(stmt)
        await self.session.flush()
