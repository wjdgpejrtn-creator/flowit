from __future__ import annotations

import uuid
from abc import ABC
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import Base

T = TypeVar("T", bound=Base)


class EntityNotFoundError(Exception):
    pass


class BaseRepository(ABC, Generic[T]):
    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for base in getattr(cls, "__orig_bases__", ()):
            if hasattr(base, "__args__"):
                args = base.__args__
                if args and isinstance(args[0], type) and issubclass(args[0], Base):
                    cls.model = args[0]
                    break

    async def create(self, **kwargs: Any) -> T:
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def get(self, entity_id: uuid.UUID) -> T | None:
        return await self.session.get(self.model, entity_id)

    async def get_or_raise(self, entity_id: uuid.UUID) -> T:
        instance = await self.get(entity_id)
        if instance is None:
            raise EntityNotFoundError(
                f"{self.model.__name__} with id={entity_id} not found"
            )
        return instance

    async def update(self, entity_id: uuid.UUID, **kwargs: Any) -> T | None:
        instance = await self.get(entity_id)
        if instance is None:
            return None
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, entity_id: uuid.UUID) -> bool:
        instance = await self.get(entity_id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: str | None = None,
    ) -> Sequence[T]:
        limit = min(limit, 1000)
        stmt = select(self.model).offset(offset).limit(limit)

        if order_by is not None:
            descending = order_by.startswith("-")
            col_name = order_by.lstrip("-")
            col = getattr(self.model, col_name, None)
            if col is not None:
                stmt = stmt.order_by(col.desc() if descending else col.asc())

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()
