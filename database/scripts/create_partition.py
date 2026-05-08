"""Create monthly node_logs partitions for the next N months.

Usage:
    DATABASE_URL=postgresql+asyncpg://... python -m database.scripts.create_partition --months 3
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from sqlalchemy import text

from src.engine import get_engine


async def create_partitions(months_ahead: int = 3) -> list[str]:
    engine = get_engine()
    created: list[str] = []
    today = date.today().replace(day=1)

    async with engine.begin() as conn:
        for i in range(months_ahead):
            start = today + timedelta(days=32 * i)
            start = start.replace(day=1)
            end = (start + timedelta(days=32)).replace(day=1)

            partition_name = f"node_logs_{start.strftime('%Y_%m')}"
            sql = f"""
                CREATE TABLE IF NOT EXISTS {partition_name}
                PARTITION OF node_logs
                FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}');
            """
            await conn.execute(text(sql))
            created.append(partition_name)

    await engine.dispose()
    return created


async def main() -> None:
    months = 3
    if "--months" in sys.argv:
        idx = sys.argv.index("--months")
        months = int(sys.argv[idx + 1])

    partitions = await create_partitions(months)
    print(f"Created/verified {len(partitions)} partitions:")
    for name in partitions:
        print(f"  - {name}")


if __name__ == "__main__":
    asyncio.run(main())
