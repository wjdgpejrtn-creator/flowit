"""Apply database/schemas/*.sql files via the tracking-aware MigrationRunner.

Modes:
    (default)   Apply pending migrations + backfill bootstrap on a fresh
                schema_migrations table when declared tables already exist.
    --status    Read-only — show which files would be applied/skipped/backfilled
                without touching the DB.
    --dry-run   Same as --status (kept for familiarity with other tools).

Usage:
    DATABASE_URL=postgresql+asyncpg://... python -m database.scripts.migrate
    python -m database.scripts.migrate --status

Connection:
    Honours DATABASE_URL today (legacy). IAM-based connection helpers are
    provided by `database/scripts/diagnose.py` — Phase 1 keeps this script
    backwards-compatible; switching to a shared IAM connect helper is a
    follow-up (ADR-0008 §future-work).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.engine import get_engine  # noqa: E402
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


async def _run(*, dry_run: bool) -> int:
    engine = get_engine()
    runner = MigrationRunner(engine)
    try:
        steps = await runner.run_schemas(dry_run=dry_run)
    except MigrationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()

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
