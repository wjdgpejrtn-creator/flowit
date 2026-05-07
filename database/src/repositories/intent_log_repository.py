from __future__ import annotations

from src.models.intent_log import IntentLogModel
from src.repositories.base import BaseRepository


class IntentLogRepository(BaseRepository[IntentLogModel]):
    async def append(self, **kwargs) -> None:
        await self.create(**kwargs)
