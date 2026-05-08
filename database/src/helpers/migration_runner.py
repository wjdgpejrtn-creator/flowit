from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


class MigrationRunner:
    """Execute raw SQL schema files and track applied migrations."""

    def __init__(
        self,
        engine: AsyncEngine,
        schemas_dir: Path | None = None,
    ) -> None:
        self._engine = engine
        self._schemas_dir = schemas_dir or Path(__file__).parents[2] / "schemas"

    async def run_schemas(self) -> list[str]:
        applied: list[str] = []
        sql_files = sorted(self._schemas_dir.glob("*.sql"))

        async with self._engine.begin() as conn:
            for sql_file in sql_files:
                content = sql_file.read_text(encoding="utf-8")
                await conn.execute(text(content))
                applied.append(sql_file.name)

        return applied

    async def run_single(self, filename: str) -> None:
        filepath = self._schemas_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Schema file not found: {filepath}")

        content = filepath.read_text(encoding="utf-8")
        async with self._engine.begin() as conn:
            await conn.execute(text(content))
