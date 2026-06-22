from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(*, url: str | None = None) -> AsyncEngine:
    global _engine

    if _engine is not None and url is None:
        return _engine

    database_url = url or os.getenv("DATABASE_URL")
    if database_url is None:
        raise RuntimeError(
            "DATABASE_URL environment variable is not set. "
            "Set it before importing the database module."
        )

    engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )

    if url is None:
        _engine = engine

    return engine


def create_session_factory(
    engine: AsyncEngine | None = None,
) -> async_sessionmaker[AsyncSession]:
    global _session_factory

    if _session_factory is not None and engine is None:
        return _session_factory

    resolved_engine = engine or get_engine()
    factory = async_sessionmaker(
        bind=resolved_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    if engine is None:
        _session_factory = factory

    return factory


@asynccontextmanager
async def get_session(
    engine: AsyncEngine | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    factory = create_session_factory(engine)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
