"""Apply all SQL schema files to the database.

Usage:
    DATABASE_URL=postgresql+asyncpg://... python -m database.scripts.migrate
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.engine import get_engine
from src.helpers.migration_runner import MigrationRunner


async def main() -> None:
    engine = get_engine()
    runner = MigrationRunner(engine)
    applied = await runner.run_schemas()
    print(f"Applied {len(applied)} schema files:")
    for name in applied:
        print(f"  - {name}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
