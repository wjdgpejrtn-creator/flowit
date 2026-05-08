"""Cloud SQL IAM 인증 접속 테스트.

사용법:
    .env 에 아래 3개 환경변수 설정 후 실행
        CLOUD_SQL_INSTANCE=<GCP_PROJECT_ID>:<REGION>:<INSTANCE>
        DB_IAM_USER=본인이메일@gmail.com
        DB_NAME=workflow_automation

    python scripts/test_iam_connection.py
"""

import asyncio
import os

from google.cloud.sql.connector import Connector
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

INSTANCE = os.getenv("CLOUD_SQL_INSTANCE")
IAM_USER = os.getenv("DB_IAM_USER")
DB_NAME = os.getenv("DB_NAME")


async def test():
    if not all([INSTANCE, IAM_USER, DB_NAME]):
        print("[FAIL] 환경변수 누락: CLOUD_SQL_INSTANCE, DB_IAM_USER, DB_NAME 확인")
        return

    loop = asyncio.get_running_loop()
    connector = Connector(loop=loop)

    async def getconn():
        return await connector.connect_async(
            INSTANCE, "asyncpg", user=IAM_USER, db=DB_NAME, enable_iam_auth=True,
        )

    engine = create_async_engine("postgresql+asyncpg://", async_creator=getconn)

    async with engine.begin() as conn:
        r = await conn.execute(text("SELECT version()"))
        print(f"[OK] PostgreSQL: {r.scalar()}")

        r = await conn.execute(
            text("SELECT extname, extversion FROM pg_extension WHERE extname IN ('pgcrypto','vector')")
        )
        for row in r.fetchall():
            print(f"[OK] Extension: {row[0]} v{row[1]}")

        r = await conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        )
        print(f"[OK] Public tables: {r.scalar()}")

    await engine.dispose()
    await connector.close_async()
    print("\n=== IAM auth connection test PASSED ===")


if __name__ == "__main__":
    asyncio.run(test())
