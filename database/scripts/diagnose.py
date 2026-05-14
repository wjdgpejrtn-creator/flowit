"""staging Cloud SQL 적용 상태 진단 스크립트.

PR #54 (Personalization sub-agent) unblock + REQ-001 마이그레이션 운영성 작업의
Phase 0 진단용. 어떤 .sql 파일이 적용됐는지, 핵심 테이블이 존재하는지,
extensions가 깔려 있는지 한 번에 점검하고 결과를 stdout + JSON 파일로 출력한다.

요구 환경 변수 (.env 또는 직접 export):
    CLOUD_SQL_INSTANCE   <PROJECT>:<REGION>:<INSTANCE>
    DB_IAM_USER          <user>@gmail.com (본인 IAM 계정)
    DB_NAME              workflow_automation

사전 준비:
    gcloud auth application-default login   (1회)
    uv pip install cloud-sql-python-connector[asyncpg] sqlalchemy[asyncio] asyncpg

실행 (PowerShell, repo root):
    $env:PYTHONUTF8 = "1"
    python -m database.scripts.diagnose

종료 코드:
    0 — 접속 OK + PR #54 필요 테이블/확장 모두 존재
    1 — 접속은 됐지만 PR #54 차단 요인 있음
    2 — 의존성 미설치 또는 환경 변수 누락
    3 — 접속 자체 실패
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from google.cloud.sql.connector import Connector, IPTypes
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
except ImportError as exc:
    print(f"[FAIL] missing dependency: {exc}", file=sys.stderr)
    print(
        "       run: uv pip install cloud-sql-python-connector[asyncpg] "
        "sqlalchemy[asyncio] asyncpg",
        file=sys.stderr,
    )
    sys.exit(2)


SCHEMAS_DIR = Path(__file__).parents[1] / "schemas"
OUTPUT_JSON = Path(__file__).parent / ".diagnose_output.json"

CORE_TABLES_FOR_PR54 = ["users", "agent_memories"]
REQUIRED_EXTENSIONS = ["pgcrypto", "vector"]


@dataclass
class SchemaFile:
    filename: str
    declared_tables: list[str]
    existing_tables: list[str] = field(default_factory=list)
    missing_tables: list[str] = field(default_factory=list)

    @property
    def state(self) -> str:
        if not self.declared_tables:
            return "no-tables-declared"
        if not self.missing_tables:
            return "applied"
        if self.existing_tables:
            return "partial"
        return "not-applied"


@dataclass
class DiagnosisResult:
    cloud_sql_instance: str
    db_user: str
    db_name: str
    connection_ok: bool
    error: str | None = None
    pg_version: str | None = None
    extensions: dict[str, str | None] = field(default_factory=dict)
    schema_migrations_tracking_exists: bool = False
    all_public_tables: list[str] = field(default_factory=list)
    schema_files: list[SchemaFile] = field(default_factory=list)
    pr54_ready: bool = False
    pr54_blockers: list[str] = field(default_factory=list)


_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\"?\w+\"?\.)?\"?(\w+)\"?",
    re.IGNORECASE,
)


def _parse_declared_tables(sql_path: Path) -> list[str]:
    sql_text = sql_path.read_text(encoding="utf-8")
    declared: list[str] = []
    for match in _CREATE_TABLE_RE.finditer(sql_text):
        table = match.group(1).lower()
        if table not in declared:
            declared.append(table)
    return declared


async def _diagnose() -> DiagnosisResult:
    instance = os.environ.get("CLOUD_SQL_INSTANCE", "")
    user = os.environ.get("DB_IAM_USER", "")
    db = os.environ.get("DB_NAME", "")

    result = DiagnosisResult(
        cloud_sql_instance=instance,
        db_user=user,
        db_name=db,
        connection_ok=False,
    )

    if not (instance and user and db):
        result.error = (
            "Missing one of CLOUD_SQL_INSTANCE / DB_IAM_USER / DB_NAME "
            "(see docs/guides/cloud-sql-setup.md §7)"
        )
        return result

    connector = Connector()

    async def getconn():
        return await connector.connect_async(
            instance,
            "asyncpg",
            user=user,
            db=db,
            enable_iam_auth=True,
            ip_type=IPTypes.PUBLIC,
        )

    engine = create_async_engine("postgresql+asyncpg://", async_creator=getconn)

    try:
        async with engine.connect() as conn:
            result.connection_ok = True
            result.pg_version = (await conn.execute(text("SELECT version()"))).scalar()

            ext_rows = (
                await conn.execute(
                    text(
                        "SELECT extname, extversion FROM pg_extension "
                        "WHERE extname = ANY(:names)"
                    ),
                    {"names": REQUIRED_EXTENSIONS},
                )
            ).all()
            ext_map = {row.extname: row.extversion for row in ext_rows}
            result.extensions = {name: ext_map.get(name) for name in REQUIRED_EXTENSIONS}

            tables = (
                await conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_type='BASE TABLE' "
                        "ORDER BY table_name"
                    )
                )
            ).all()
            result.all_public_tables = [row.table_name for row in tables]
            result.schema_migrations_tracking_exists = (
                "schema_migrations" in result.all_public_tables
            )

            existing_set = set(result.all_public_tables)
            for sql_path in sorted(SCHEMAS_DIR.glob("*.sql")):
                declared = _parse_declared_tables(sql_path)
                sf = SchemaFile(filename=sql_path.name, declared_tables=declared)
                sf.existing_tables = [t for t in declared if t in existing_set]
                sf.missing_tables = [t for t in declared if t not in existing_set]
                result.schema_files.append(sf)

            blockers: list[str] = []
            for tbl in CORE_TABLES_FOR_PR54:
                if tbl not in existing_set:
                    blockers.append(f"missing table: {tbl}")
            if not result.extensions.get("pgcrypto"):
                blockers.append("missing extension: pgcrypto (gen_random_uuid)")
            result.pr54_blockers = blockers
            result.pr54_ready = not blockers

    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        await engine.dispose()
        await connector.close_async()

    return result


def _print_human(result: DiagnosisResult) -> None:
    bar = "=" * 72
    print(bar)
    print("Staging Cloud SQL — Diagnosis")
    print(bar)
    print(f"  instance : {result.cloud_sql_instance or '(unset)'}")
    print(f"  user     : {result.db_user or '(unset)'}")
    print(f"  db       : {result.db_name or '(unset)'}")
    print()

    if not result.connection_ok:
        print(f"[FAIL] connection: {result.error}")
        return

    print(f"[OK]   connection — {result.pg_version}")
    print()

    print("Extensions:")
    for name in REQUIRED_EXTENSIONS:
        ver = result.extensions.get(name)
        mark = "[OK]  " if ver else "[MISS]"
        print(f"  {mark} {name:10} {ver or '(not installed)'}")
    print()

    tracking = "present" if result.schema_migrations_tracking_exists else "MISSING (Phase 1 will add)"
    print(f"Tracking table 'schema_migrations': {tracking}")
    print()

    print(f"Public tables ({len(result.all_public_tables)}):")
    if result.all_public_tables:
        for tbl in result.all_public_tables:
            print(f"  - {tbl}")
    else:
        print("  (none — fresh database)")
    print()

    print("Schema file applied state:")
    marks = {"applied": "OK ", "partial": "~~ ", "not-applied": "XX ", "no-tables-declared": ".. "}
    for sf in result.schema_files:
        print(f"  [{marks[sf.state]}] {sf.filename:50} {sf.state}")
        if sf.missing_tables:
            print(f"           missing: {', '.join(sf.missing_tables)}")
    print()

    print("PR #54 readiness:")
    if result.pr54_ready:
        print("  [OK] required tables/extensions present — save_memory action will work")
    else:
        for blocker in result.pr54_blockers:
            print(f"  [BLOCK] {blocker}")
    print()
    print(f"JSON dump → {OUTPUT_JSON}")


def _serialize(result: DiagnosisResult) -> dict[str, Any]:
    return asdict(result)


async def main() -> None:
    result = await _diagnose()
    _print_human(result)
    OUTPUT_JSON.write_text(
        json.dumps(_serialize(result), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if not result.connection_ok:
        sys.exit(3)
    sys.exit(0 if result.pr54_ready else 1)


if __name__ == "__main__":
    asyncio.run(main())
