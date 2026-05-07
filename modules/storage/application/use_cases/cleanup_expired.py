from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.ports.object_storage_port import ObjectStoragePort
from ...orm.storage_object_model import StorageObjectModel


class CleanupExpiredUseCase:
    def __init__(self, session: AsyncSession, storage: ObjectStoragePort) -> None:
        self._session = session
        self._storage = storage

    async def execute(self) -> int:
        stmt = select(StorageObjectModel).where(
            StorageObjectModel.expires_at.isnot(None),
            StorageObjectModel.expires_at < datetime.now(timezone.utc),
        )
        result = await self._session.execute(stmt)
        expired = result.scalars().all()

        count = 0
        for model in expired:
            try:
                await self._storage.delete(model.key)
            except Exception:
                continue
            await self._session.delete(model)
            count += 1

        await self._session.flush()
        return count
