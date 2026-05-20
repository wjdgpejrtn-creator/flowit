from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.entities.credential import Credential, CredentialKind
from auth.domain.ports.credential_repository import CredentialRepository

from ..mappers.credential_mapper import CredentialMapper
from ..orm.credential_model import CredentialModel


class PgCredentialRepository(CredentialRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: UUID,
        name: str,
        credential_kind: CredentialKind,
        encrypted_data: bytes,
        metadata: dict[str, Any] | None = None,
    ) -> Credential:
        now = datetime.now(timezone.utc)
        model = CredentialModel(
            credential_id=uuid4(),
            user_id=user_id,
            name=name,
            credential_kind=credential_kind,
            encrypted_data=encrypted_data,
            credential_metadata=metadata or {},
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.flush()
        return CredentialMapper.to_domain(model)

    async def get_by_id(self, credential_id: UUID) -> Optional[Credential]:
        stmt = select(CredentialModel).where(CredentialModel.credential_id == credential_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return CredentialMapper.to_domain(model)

    async def update_data(self, credential_id: UUID, encrypted_data: bytes) -> None:
        stmt = (
            update(CredentialModel)
            .where(CredentialModel.credential_id == credential_id)
            .values(encrypted_data=encrypted_data, updated_at=datetime.now(timezone.utc))
        )
        await self._session.execute(stmt)
