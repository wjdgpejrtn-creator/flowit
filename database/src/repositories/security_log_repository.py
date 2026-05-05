from __future__ import annotations

from src.models.security_log import SecurityLogModel
from src.repositories.base import BaseRepository


class SecurityLogRepository(BaseRepository[SecurityLogModel]):
    async def append(self, **kwargs) -> None:
        await self.create(**kwargs)
