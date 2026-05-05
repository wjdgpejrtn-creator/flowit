"""Test fixtures for database integration tests.

Uses testcontainers to spin up a real PostgreSQL 16 + pgvector instance.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.models.base import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create a test database engine using testcontainers."""
    try:
        from testcontainers.postgres import PostgresContainer

        with PostgresContainer("pgvector/pgvector:pg16") as pg:
            url = pg.get_connection_url().replace("psycopg2", "asyncpg")
            engine = create_async_engine(url)

            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)

            yield engine
            await engine.dispose()
    except ImportError:
        pytest.skip("testcontainers not installed")


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Provide a transactional session that rolls back after each test."""
    factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
        await session.rollback()
