"""
DB 연결 테스트 — 읽기 + 쓰기 + 삭제 (트랜잭션 롤백으로 실제 데이터 영향 없음)
실행: uv run python _test_db.py
사전 조건: gcloud auth application-default login 완료, .env 파일 존재
"""
from __future__ import annotations

import asyncio
import os
import warnings
from pathlib import Path

# google.auth quota_project warning 억제
warnings.filterwarnings("ignore", category=UserWarning, module="google.auth")

# .env 수동 로드 (python-dotenv 없어도 동작)
env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


async def main() -> None:
    instance = os.environ.get("CLOUD_SQL_INSTANCE")
    iam_user = os.environ.get("DB_IAM_USER")
    db_name = os.environ.get("DB_NAME")

    if not instance:
        print("[SKIP] CLOUD_SQL_INSTANCE 환경변수 없음")
        return

    print(f"  인스턴스 : {instance}")
    print(f"  IAM 사용자: {iam_user}")
    print(f"  DB 이름  : {db_name}")
    print()

    from google.cloud.sql.connector import Connector

    loop = asyncio.get_running_loop()
    connector = Connector(loop=loop, refresh_strategy="lazy")

    try:
        # asyncpg 연결을 직접 획득 (SQLAlchemy 그린렛 우회)
        conn = await connector.connect_async(
            instance,
            "asyncpg",
            user=iam_user,
            db=db_name,
            enable_iam_auth=True,
        )

        try:
            # 1) PostgreSQL 버전
            row = await conn.fetchval("SELECT version()")
            print(f"[OK] PostgreSQL : {row}")

            # 2) pgvector 확장
            row = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
            )
            if row:
                print(f"[OK] pgvector   : {row}")
            else:
                print("[WARN] pgvector 확장이 설치되지 않았습니다")

            # 3) pgcrypto 확장
            row = await conn.fetchval(
                "SELECT extversion FROM pg_extension WHERE extname = 'pgcrypto'"
            )
            print(f"[OK] pgcrypto   : {row}")

            # 4) public 스키마 테이블 수
            count = await conn.fetchval(
                "SELECT count(*) FROM information_schema.tables"
                " WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
            print(f"[OK] 테이블 수  : {count}개")

            # 5) node_definitions 테이블 존재 여부
            exists = await conn.fetchval(
                "SELECT EXISTS("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_schema='public' AND table_name='node_definitions'"
                ")"
            )
            print(f"[OK] node_definitions: {'있음' if exists else '없음 (마이그레이션 필요)'}")

            print()

            # --- 쓰기 / 읽기 / 삭제 테스트 (트랜잭션 롤백) ---
            async with conn.transaction():
                # 6) 임시 테이블 생성 + INSERT
                await conn.execute(
                    "CREATE TEMP TABLE _db_test (id serial PRIMARY KEY, msg text)"
                )
                await conn.execute(
                    "INSERT INTO _db_test (msg) VALUES ($1)", "hello from army5833"
                )
                print("[OK] INSERT      : 완료")

                # 7) SELECT 확인
                msg = await conn.fetchval("SELECT msg FROM _db_test WHERE id = 1")
                assert msg == "hello from army5833", f"예상값 불일치: {msg}"
                print(f"[OK] SELECT      : '{msg}'")

                # 8) DELETE
                deleted = await conn.fetchval(
                    "DELETE FROM _db_test WHERE id = 1 RETURNING id"
                )
                assert deleted == 1
                print(f"[OK] DELETE      : id={deleted} 삭제")

                # TEMP 테이블이므로 세션 종료 시 자동 삭제됨 — ROLLBACK 불필요
                print("[OK] 쓰기/읽기/삭제 모두 정상")

        finally:
            await conn.close()

    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}")
        raise
    finally:
        await connector.close_async()

    print()
    print("접속 테스트 완료")


if __name__ == "__main__":
    asyncio.run(main())
