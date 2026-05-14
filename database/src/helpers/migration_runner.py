"""Idempotent migration runner with tracking + bootstrap support.

Applies `database/schemas/*.sql` files to the database, tracking each via the
`schema_migrations` table. Three execution modes per file:

1. **Apply** — file not in tracking table → execute SQL, record hash.
2. **Skip** — file already applied with matching hash → no-op.
3. **Backfill (bootstrap)** — file not in tracking table BUT all its declared
   tables already exist in the database → mark as applied without executing.
   This handles staging databases that were migrated before the tracking table
   existed.

Hash mismatch (file changed after being applied) raises `MigrationError` — the
file must be split into a new migration rather than edited in place.

Schema isolation: pass ``schema_name`` to run inside an alternate PostgreSQL
schema (search_path scoped). Used by tests to operate in a throwaway
``test_migration_<random>`` schema without touching ``public``.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

_TRACKING_FILE = "000_migration_tracking.sql"

_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:\"?\w+\"?\.)?\"?(\w+)\"?",
    re.IGNORECASE,
)

# PostgreSQL identifier validator — schema_name must be a simple lowercase
# identifier to be safely embedded in `SET search_path` (no quoting / escaping).
_VALID_SCHEMA_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied safely (e.g. hash mismatch)."""


class MigrationOutcome(str, Enum):
    APPLIED = "applied"
    SKIPPED = "skipped"
    BACKFILLED = "backfilled"


@dataclass(frozen=True)
class MigrationStep:
    filename: str
    outcome: MigrationOutcome
    sha256: str
    declared_tables: list[str]


class MigrationRunner:
    def __init__(
        self,
        engine: AsyncEngine,
        schemas_dir: Path | None = None,
        schema_name: str = "public",
    ) -> None:
        if not _VALID_SCHEMA_RE.match(schema_name):
            raise ValueError(
                f"Invalid schema_name {schema_name!r}: must match {_VALID_SCHEMA_RE.pattern}"
            )
        self._engine = engine
        self._schemas_dir = schemas_dir or Path(__file__).parents[2] / "schemas"
        self._schema_name = schema_name

    async def run_schemas(self, *, dry_run: bool = False) -> list[MigrationStep]:
        """Apply all *.sql files, returning the outcome of each step.

        If ``dry_run`` is True, no SQL is executed and the tracking table is not
        modified — the returned outcomes describe what *would* happen.
        """
        sql_files = sorted(self._schemas_dir.glob("*.sql"))
        if not sql_files:
            return []

        tracking_path = self._schemas_dir / _TRACKING_FILE
        if not tracking_path.exists():
            raise MigrationError(
                f"Tracking schema file not found: {tracking_path}. "
                f"It must exist and be the lexicographically first .sql file."
            )

        steps: list[MigrationStep] = []
        async with self._engine.begin() as conn:
            await self._set_search_path(conn)
            await self._ensure_tracking_table(conn, tracking_path, dry_run=dry_run)
            existing_tables = await self._existing_tables(conn)
            applied_records = await self._load_applied(conn)

            for sql_path in sql_files:
                if sql_path.name == _TRACKING_FILE:
                    continue
                step = await self._process_file(
                    conn,
                    sql_path,
                    applied_records=applied_records,
                    existing_tables=existing_tables,
                    dry_run=dry_run,
                )
                steps.append(step)
                if step.outcome is MigrationOutcome.APPLIED:
                    existing_tables.update(step.declared_tables)

        return steps

    async def _set_search_path(self, conn: AsyncConnection) -> None:
        # schema_name은 init에서 _VALID_SCHEMA_RE로 검증됨 → f-string 안전
        await conn.execute(text(f'SET search_path TO "{self._schema_name}", public'))

    async def status(self) -> list[MigrationStep]:
        """Read-only view of what run_schemas() would do, without any side effects."""
        return await self.run_schemas(dry_run=True)

    async def _ensure_tracking_table(
        self,
        conn: AsyncConnection,
        tracking_path: Path,
        *,
        dry_run: bool,
    ) -> None:
        if dry_run:
            return
        sql = tracking_path.read_text(encoding="utf-8")
        await conn.execute(text(sql))

    async def _existing_tables(self, conn: AsyncConnection) -> set[str]:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema AND table_type='BASE TABLE'"
                ),
                {"schema": self._schema_name},
            )
        ).all()
        return {row.table_name for row in rows}

    async def _load_applied(self, conn: AsyncConnection) -> dict[str, str]:
        try:
            rows = (
                await conn.execute(
                    text("SELECT filename, sha256 FROM schema_migrations")
                )
            ).all()
        except Exception:
            return {}
        return {row.filename: row.sha256 for row in rows}

    async def _process_file(
        self,
        conn: AsyncConnection,
        sql_path: Path,
        *,
        applied_records: dict[str, str],
        existing_tables: set[str],
        dry_run: bool,
    ) -> MigrationStep:
        content = sql_path.read_text(encoding="utf-8")
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        declared = _parse_declared_tables(content)

        recorded_hash = applied_records.get(sql_path.name)
        if recorded_hash is not None:
            if recorded_hash != sha:
                raise MigrationError(
                    f"Hash mismatch for {sql_path.name}: "
                    f"recorded={recorded_hash[:12]}…, current={sha[:12]}…. "
                    f"Schema files are immutable once applied — split into a new migration."
                )
            return MigrationStep(sql_path.name, MigrationOutcome.SKIPPED, sha, declared)

        if declared and all(t in existing_tables for t in declared):
            if not dry_run:
                await self._record(conn, sql_path.name, sha, bootstrapped=True)
            return MigrationStep(sql_path.name, MigrationOutcome.BACKFILLED, sha, declared)

        if not dry_run:
            await conn.execute(text(content))
            await self._record(conn, sql_path.name, sha, bootstrapped=False)
        return MigrationStep(sql_path.name, MigrationOutcome.APPLIED, sha, declared)

    async def _record(
        self,
        conn: AsyncConnection,
        filename: str,
        sha: str,
        *,
        bootstrapped: bool,
    ) -> None:
        await conn.execute(
            text(
                "INSERT INTO schema_migrations (filename, sha256, bootstrapped) "
                "VALUES (:filename, :sha, :bootstrapped)"
            ),
            {"filename": filename, "sha": sha, "bootstrapped": bootstrapped},
        )

    async def run_single(self, filename: str) -> None:
        """Apply a single schema file unconditionally (legacy compat — use run_schemas)."""
        filepath = self._schemas_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Schema file not found: {filepath}")

        content = filepath.read_text(encoding="utf-8")
        async with self._engine.begin() as conn:
            await self._set_search_path(conn)
            await conn.execute(text(content))


def _parse_declared_tables(sql_text: str) -> list[str]:
    declared: list[str] = []
    for match in _CREATE_TABLE_RE.finditer(sql_text):
        table = match.group(1).lower()
        if table not in declared:
            declared.append(table)
    return declared
