from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.domain.entities.user import User, UserRole
from auth.domain.ports.user_repository import UserRepository

from ..mappers.user_mapper import UserMapper
from ..orm.user_model import UserModel


class PgUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_id(self, user_id: UUID) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.user_id == user_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return UserMapper.to_domain(model)

    async def find_by_email(self, email: str) -> Optional[User]:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        return UserMapper.to_domain(model)

    async def create(
        self,
        user_id: UUID,
        email: str,
        name: str,
        role: UserRole = "User",
        department_id: UUID | None = None,
    ) -> User:
        now = datetime.now(timezone.utc)
        model = UserModel(
            user_id=user_id,
            email=email,
            name=name,
            role=role,
            department_id=department_id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self._session.add(model)
        await self._session.flush()
        return UserMapper.to_domain(model)

    async def update_role(self, user_id: UUID, role: UserRole) -> None:
        stmt = update(UserModel).where(UserModel.user_id == user_id).values(role=role)
        await self._session.execute(stmt)

    async def update_department(self, user_id: UUID, department_id: UUID | None) -> None:
        stmt = update(UserModel).where(UserModel.user_id == user_id).values(department_id=department_id)
        await self._session.execute(stmt)
