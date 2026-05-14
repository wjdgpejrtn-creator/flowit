-- 000_migration_tracking.sql
-- Migration tracking table — records which .sql files have been applied.
-- Loaded before all other schema files by MigrationRunner.
--
-- Idempotent: safe to run on fresh DBs and on staging that already has 16 files
-- applied (handled by MigrationRunner bootstrap logic — backfills this table
-- with existing schema files when it detects declared tables already exist).

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename     VARCHAR(255) PRIMARY KEY,
    sha256       CHAR(64)     NOT NULL,
    applied_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    applied_by   TEXT         NOT NULL DEFAULT CURRENT_USER,
    bootstrapped BOOLEAN      NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE schema_migrations IS
    'Tracks which database/schemas/*.sql files have been applied. bootstrapped=TRUE means the file was marked as applied retroactively without executing (declared tables already existed).';
