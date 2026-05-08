from __future__ import annotations

import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


_connector = None


def _build_engine():
    instance_connection_name = os.getenv("CLOUD_SQL_INSTANCE")
    pool_size = int(os.getenv("DB_POOL_SIZE", "10"))

    if instance_connection_name:
        async def _getconn():
            global _connector
            if _connector is None:
                from google.cloud.sql.connector import Connector

                _connector = Connector(loop=asyncio.get_running_loop())
            return await _connector.connect_async(
                instance_connection_name,
                "asyncpg",
                user=os.getenv("DB_IAM_USER"),
                db=os.getenv("DB_NAME"),
                enable_iam_auth=True,
            )

        return create_async_engine(
            "postgresql+asyncpg://",
            async_creator=_getconn,
            pool_size=pool_size,
            echo=False,
        )

    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    name = os.getenv("DB_NAME")
    return create_async_engine(
        f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}",
        pool_size=pool_size,
        echo=False,
    )


engine = _build_engine()

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
