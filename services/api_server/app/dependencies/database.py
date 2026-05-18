from __future__ import annotations

import logging
from typing import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings

logger = logging.getLogger(__name__)


async def _build_iam_engine(settings: Settings) -> AsyncEngine:
    # sub-agent 표준 패턴 ([[sub_agent_cloud_sql_iam]]) — cloud-sql-python-connector 비동기 IAM.
    # `create_async_connector()`(v1.10+)는 현재 이벤트 루프를 자동 캡처 + lazy refresh 기본값이라
    # async lifespan에서 안전. `Connector(loop=...)` 직접 생성보다 best practice
    # ([[staging_db_state]] line 35 권고 — sub-agent 전체가 async connector 통일).
    from google.cloud.sql.connector import IPTypes, create_async_connector

    connector = await create_async_connector()

    async def getconn():
        return await connector.connect_async(
            settings.cloud_sql_instance,
            "asyncpg",
            user=settings.db_iam_user,
            db=settings.db_name,
            enable_iam_auth=True,
            ip_type=IPTypes.PUBLIC,
        )

    engine = create_async_engine(
        "postgresql+asyncpg://",
        async_creator=getconn,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    engine.sync_engine.dispose_connector = connector  # type: ignore[attr-defined]
    return engine


def _build_dsn_engine(settings: Settings) -> AsyncEngine:
    if not settings.db_host or not settings.db_password:
        raise RuntimeError(
            "DSN fallback requires DB_HOST and DB_PASSWORD. "
            "Set CLOUD_SQL_INSTANCE + DB_IAM_USER for IAM auth (staging/prod)."
        )
    dsn = (
        f"postgresql+asyncpg://{settings.db_iam_user or 'postgres'}:"
        f"{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}"
    )
    return create_async_engine(dsn, pool_size=5, max_overflow=10, pool_pre_ping=True)


async def init_db_engine(settings: Settings) -> AsyncEngine:
    if settings.use_iam():
        logger.info("DB engine: Cloud SQL IAM (instance=%s, user=%s)", settings.cloud_sql_instance, settings.db_iam_user)
        return await _build_iam_engine(settings)
    logger.info("DB engine: DSN fallback (host=%s, db=%s) — dev only", settings.db_host, settings.db_name)
    return _build_dsn_engine(settings)


async def dispose_db_engine(engine: AsyncEngine) -> None:
    connector = getattr(engine.sync_engine, "dispose_connector", None)
    await engine.dispose()
    if connector is not None:
        await connector.close_async()


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    async with session_factory() as session:
        yield session
