"""Apply database/schemas/*.sql files via the tracking-aware MigrationRunner.

Modes:
    (default)   Apply pending migrations + backfill bootstrap on a fresh
                schema_migrations table when declared tables already exist.
    --status    Read-only — show which files would be applied/skipped/backfilled
                without touching the DB.
    --dry-run   Same as --status (kept for familiarity with other tools).

Connection (one of):
    1. CLOUD_SQL_INSTANCE + DB_IAM_USER + DB_NAME → IAM via cloud-sql-connector
       (preferred — matches docs/guides/cloud-sql-setup.md §7).
    2. DATABASE_URL=postgresql+asyncpg://... → direct DSN (legacy / proxy).

Usage (PowerShell):
    $env:CLOUD_SQL_INSTANCE = "<project>:<region>:<instance>"
    $env:DB_IAM_USER        = "<email>@gmail.com"
    $env:DB_NAME            = "workflow_automation"
    $env:PYTHONUTF8         = "1"
    python -m database.scripts.migrate --status   # 예측
    python -m database.scripts.migrate            # 실제 적용
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine  # noqa: E402

from src.helpers.migration_runner import (  # noqa: E402
    MigrationError,
    MigrationOutcome,
    MigrationRunner,
)

_GLYPHS = {
    MigrationOutcome.APPLIED: "[APPLY ]",
    MigrationOutcome.SKIPPED: "[SKIP  ]",
    MigrationOutcome.BACKFILLED: "[BACK  ]",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--status",
        action="store_true",
        help="Read-only: report planned outcomes without modifying the DB.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias for --status.",
    )
    return parser


async def _build_engine() -> tuple[AsyncEngine, object | None]:
    """IAM 환경변수가 있으면 connector, 없으면 DATABASE_URL로 fallback.

    Returns (engine, connector). connector는 IAM 모드에서만 None이 아니며
    호출자가 dispose 후 close_async()로 정리해야 한다.
    """
    instance = os.environ.get("CLOUD_SQL_INSTANCE")
    user = os.environ.get("DB_IAM_USER")
    db = os.environ.get("DB_NAME")

    if instance and user and db:
        from google.cloud.sql.connector import IPTypes, create_async_connector

        connector = await create_async_connector()

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
        return engine, connector

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "[FAIL] No DB connection configured.\n"
            "       Set CLOUD_SQL_INSTANCE + DB_IAM_USER + DB_NAME (preferred)\n"
            "       or DATABASE_URL=postgresql+asyncpg://...\n"
            "       See docs/guides/cloud-sql-setup.md §7."
        )
    engine = create_async_engine(database_url)
    return engine, None


async def _run(*, dry_run: bool) -> int:
    engine, connector = await _build_engine()
    try:
        steps = await MigrationRunner(engine).run_schemas(dry_run=dry_run)
    except MigrationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()
        if connector is not None:
            await connector.close_async()

    mode = "STATUS" if dry_run else "APPLY"
    print(f"== Migration {mode} ==")
    counts = {outcome: 0 for outcome in MigrationOutcome}
    for step in steps:
        print(f"  {_GLYPHS[step.outcome]} {step.filename}")
        counts[step.outcome] += 1

    print()
    print(
        f"Total: {len(steps)}  "
        f"applied={counts[MigrationOutcome.APPLIED]}  "
        f"skipped={counts[MigrationOutcome.SKIPPED]}  "
        f"backfilled={counts[MigrationOutcome.BACKFILLED]}"
    )
    return 0


async def main() -> None:
    args = _build_parser().parse_args()
    code = await _run(dry_run=args.status or args.dry_run)
    sys.exit(code)


if __name__ == "__main__":
    asyncio.run(main())
