from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def get_database_url() -> str:
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    name = os.getenv("DB_NAME")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


engine = create_async_engine(
    get_database_url(),
    pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
    echo=False,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
