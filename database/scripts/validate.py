"""Validate SQL schema files by dry-running against a temporary database.

Usage:
    DATABASE_URL=postgresql+asyncpg://... python -m database.scripts.validate
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from sqlalchemy import text

from src.engine import get_engine
from src.helpers.migration_runner import MigrationRunner


async def main() -> None:
    engine = get_engine()
    runner = MigrationRunner(engine)

    try:
        applied = await runner.run_schemas()
        print(f"All {len(applied)} schema files are valid SQL.")

        async with engine.begin() as conn:
            result = await conn.execute(text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
            ))
            tables = [row[0] for row in result.fetchall()]
            print(f"\nCreated {len(tables)} tables:")
            for t in tables:
                print(f"  - {t}")

    except Exception as e:
        print(f"Schema validation FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
