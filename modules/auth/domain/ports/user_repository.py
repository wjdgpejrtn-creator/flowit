from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from ..entities.user import User, UserRole


class UserRepository(ABC):
    """User 정보 조회/관리 Port. 구현체는 modules/storage/repositories/."""

    @abstractmethod
    async def find_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def find_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def create(
        self,
        user_id: UUID,
        email: str,
        name: str,
        role: UserRole = "User",
        department_id: UUID | None = None,
    ) -> User: ...

    @abstractmethod
    async def update_role(self, user_id: UUID, role: UserRole) -> None: ...

    @abstractmethod
    async def update_department(self, user_id: UUID, department_id: UUID | None) -> None: ...
