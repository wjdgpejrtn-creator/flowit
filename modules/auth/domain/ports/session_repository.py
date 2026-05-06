from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from ..entities.session import Session


class SessionRepository(ABC):
    @abstractmethod
    async def create(self, user_id: UUID, session_hash: str, expires_at: datetime) -> Session: ...

    @abstractmethod
    async def find_by_hash(self, session_hash: str) -> Session: ...

    @abstractmethod
    async def revoke(self, session_id: UUID) -> None: ...

    @abstractmethod
    async def revoke_all_for_user(self, user_id: UUID) -> int: ...
