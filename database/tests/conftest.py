"""Test fixtures for database integration tests.

Supports three backends (in priority order):
  1. DATABASE_URL env var → connect directly
  2. database/.env with DB_PASSWORD → build URL for Cloud SQL proxy (127.0.0.1:5432)
  3. No config → testcontainers (requires Docker)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.models.base import Base


def _resolve_database_url() -> str | None:
    url = os.getenv("DATABASE_URL")
    if url:
        return url

    env_file = Path(__file__).parents[1] / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)

    password = os.getenv("DB_PASSWORD")
    if password:
        host = os.getenv("DB_HOST", "127.0.0.1")
        port = os.getenv("DB_PORT", "5432")
        user = os.getenv("DB_USER", "postgres")
        dbname = os.getenv("DB_NAME", "workflow_automation")
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}"

    return None


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine():
    """Create a test database engine."""
    database_url = _resolve_database_url()

    if database_url:
        if "asyncpg" not in database_url:
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")
            database_url = database_url.replace("postgres://", "postgresql+asyncpg://")
        engine = create_async_engine(database_url)
        async with engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        yield engine
        await engine.dispose()
    else:
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
            pytest.skip("DATABASE_URL not set and testcontainers not installed")


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(db_engine):
    """Provide a transactional session that rolls back after each test."""
    factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
        await session.rollback()
