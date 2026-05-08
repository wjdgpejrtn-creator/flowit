"""Load initial seed data (node_definitions 54 MVP types).

Usage:
    DATABASE_URL=postgresql+asyncpg://... python -m database.scripts.seed
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.engine import get_engine, get_session
from src.repositories.node_definition_repository import NodeDefinitionRepository


SEEDS_DIR = Path(__file__).parents[1] / "seeds"


async def seed_node_definitions() -> int:
    seed_file = SEEDS_DIR / "node_definitions.json"
    if not seed_file.exists():
        print(f"Seed file not found: {seed_file}")
        return 0

    data = json.loads(seed_file.read_text(encoding="utf-8"))
    count = 0

    async with get_session() as session:
        repo = NodeDefinitionRepository(session)
        for item in data:
            await repo.upsert(**item)
            count += 1

    return count


async def main() -> None:
    count = await seed_node_definitions()
    print(f"Seeded {count} node definitions.")
    from src.engine import dispose_engine
    await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
