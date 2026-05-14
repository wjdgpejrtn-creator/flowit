"""MigrationRunner 시나리오 검증 — staging Cloud SQL의 격리된 임시 schema에서.

[[team_local_env_policy]] 준수: 로컬 Docker(testcontainers) 미사용. staging
Cloud SQL에 IAM 인증으로 접속해, 매 테스트마다 `test_migration_<random>`
schema를 만들어 그 안에서 작업한 뒤 drop한다. public schema에는 손대지 않음.

요구 환경 변수:
    CLOUD_SQL_INSTANCE   <PROJECT>:<REGION>:<INSTANCE>
    DB_IAM_USER          <user>@gmail.com
    DB_NAME              workflow_automation

사전 준비:
    gcloud auth application-default login
    uv pip install -e database/.[dev]

실행:
    $env:PYTHONUTF8 = "1"
    python -m pytest database/tests/test_migration_runner.py -v

5가지 흐름:
  1. fresh apply         — 빈 schema에 .sql 적용 + tracking 기록.
  2. skip on rerun       — 같은 파일 재실행 → SKIPPED.
  3. bootstrap backfill  — 사전에 declared 테이블이 존재하면 실행 없이 mark.
  4. hash mismatch       — 적용된 파일 내용 변경 시 fail-loud.
  5. dry-run             — 어떤 부수효과도 남기지 않음.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.helpers.migration_runner import (  # noqa: E402
    MigrationError,
    MigrationOutcome,
    MigrationRunner,
)

pytestmark = pytest.mark.asyncio

_TRACKING_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename     VARCHAR(255) PRIMARY KEY,
    sha256       CHAR(64)     NOT NULL,
    applied_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    applied_by   TEXT         NOT NULL DEFAULT CURRENT_USER,
    bootstrapped BOOLEAN      NOT NULL DEFAULT FALSE
);
"""

_REQUIRED_ENV = ("CLOUD_SQL_INSTANCE", "DB_IAM_USER", "DB_NAME")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def iam_engine():
    missing = [k for k in _REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        pytest.skip(f"IAM env vars missing: {', '.join(missing)}")

    try:
        from google.cloud.sql.connector import IPTypes, create_async_connector
    except ImportError:
        pytest.skip("cloud-sql-python-connector not installed")

    connector = await create_async_connector()

    async def getconn():
        return await connector.connect_async(
            os.environ["CLOUD_SQL_INSTANCE"],
            "asyncpg",
            user=os.environ["DB_IAM_USER"],
            db=os.environ["DB_NAME"],
            enable_iam_auth=True,
            ip_type=IPTypes.PUBLIC,
        )

    engine = create_async_engine("postgresql+asyncpg://", async_creator=getconn)
    try:
        yield engine
    finally:
        await engine.dispose()
        await connector.close_async()


@pytest_asyncio.fixture(loop_scope="session")
async def isolated_schema(iam_engine):
    """매 테스트마다 고유한 schema를 생성하고, 끝나면 drop."""
    schema = f"test_mig_{uuid.uuid4().hex[:12]}"
    async with iam_engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        yield schema
    finally:
        async with iam_engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


@pytest.fixture
def schemas_dir(tmp_path):
    d = tmp_path / "schemas"
    d.mkdir()
    (d / "000_migration_tracking.sql").write_text(_TRACKING_SQL, encoding="utf-8")
    return d


def _write(schemas_dir: Path, filename: str, content: str) -> Path:
    path = schemas_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


async def _tables_in(engine, schema: str) -> set[str]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema AND table_type='BASE TABLE'"
                ),
                {"schema": schema},
            )
        ).all()
    return {row.table_name for row in rows}


async def _migrations_rows(engine, schema: str) -> list[tuple[str, bool]]:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    f'SELECT filename, bootstrapped FROM "{schema}".schema_migrations '
                    "ORDER BY filename"
                )
            )
        ).all()
    return [(r.filename, r.bootstrapped) for r in rows]


async def test_fresh_apply(iam_engine, isolated_schema, schemas_dir):
    _write(schemas_dir, "001_widgets.sql", "CREATE TABLE widgets (id SERIAL PRIMARY KEY);")
    _write(schemas_dir, "002_gadgets.sql", "CREATE TABLE gadgets (id SERIAL PRIMARY KEY);")

    runner = MigrationRunner(iam_engine, schemas_dir=schemas_dir, schema_name=isolated_schema)
    steps = await runner.run_schemas()

    assert [s.outcome for s in steps] == [
        MigrationOutcome.APPLIED,
        MigrationOutcome.APPLIED,
    ]
    tables = await _tables_in(iam_engine, isolated_schema)
    assert {"widgets", "gadgets", "schema_migrations"} <= tables

    assert await _migrations_rows(iam_engine, isolated_schema) == [
        ("001_widgets.sql", False),
        ("002_gadgets.sql", False),
    ]


async def test_skip_on_rerun(iam_engine, isolated_schema, schemas_dir):
    _write(schemas_dir, "001_widgets.sql", "CREATE TABLE widgets (id SERIAL PRIMARY KEY);")
    runner = MigrationRunner(iam_engine, schemas_dir=schemas_dir, schema_name=isolated_schema)

    await runner.run_schemas()
    steps = await runner.run_schemas()

    assert steps[0].outcome is MigrationOutcome.SKIPPED


async def test_bootstrap_backfill(iam_engine, isolated_schema, schemas_dir):
    _write(schemas_dir, "001_widgets.sql", "CREATE TABLE widgets (id SERIAL PRIMARY KEY);")

    # 사전에 widgets만 격리 schema에 생성 (추적 테이블은 없는 상태)
    async with iam_engine.begin() as conn:
        await conn.execute(
            text(f'CREATE TABLE "{isolated_schema}".widgets (id SERIAL PRIMARY KEY)')
        )

    runner = MigrationRunner(iam_engine, schemas_dir=schemas_dir, schema_name=isolated_schema)
    steps = await runner.run_schemas()

    assert steps[0].outcome is MigrationOutcome.BACKFILLED
    assert await _migrations_rows(iam_engine, isolated_schema) == [
        ("001_widgets.sql", True),
    ]


async def test_hash_mismatch_fails_loud(iam_engine, isolated_schema, schemas_dir):
    f = _write(schemas_dir, "001_widgets.sql", "CREATE TABLE widgets (id SERIAL PRIMARY KEY);")
    runner = MigrationRunner(iam_engine, schemas_dir=schemas_dir, schema_name=isolated_schema)
    await runner.run_schemas()

    f.write_text(
        "CREATE TABLE widgets (id SERIAL PRIMARY KEY, name TEXT);",
        encoding="utf-8",
    )

    with pytest.raises(MigrationError, match="Hash mismatch"):
        await runner.run_schemas()


async def test_dry_run_has_no_side_effects(iam_engine, isolated_schema, schemas_dir):
    _write(schemas_dir, "001_widgets.sql", "CREATE TABLE widgets (id SERIAL PRIMARY KEY);")

    runner = MigrationRunner(iam_engine, schemas_dir=schemas_dir, schema_name=isolated_schema)
    steps = await runner.status()

    assert steps[0].outcome is MigrationOutcome.APPLIED  # would-apply
    tables = await _tables_in(iam_engine, isolated_schema)
    assert "widgets" not in tables
    assert "schema_migrations" not in tables


def test_invalid_schema_name_rejected(iam_engine, schemas_dir):
    """search_path SQL injection 방지 검증 — schema_name 정규식 위반은 ValueError."""
    with pytest.raises(ValueError, match="Invalid schema_name"):
        MigrationRunner(iam_engine, schemas_dir=schemas_dir, schema_name="public; DROP TABLE foo")
