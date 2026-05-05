-- 003_node_logs_partitioned.sql
-- RANGE partitioned by started_at (monthly) for high-volume node execution logs

-- ============================================================
-- node_logs (parent, partitioned)
-- ============================================================
CREATE TABLE node_logs (
    id              UUID NOT NULL DEFAULT gen_random_uuid(),
    execution_id    UUID NOT NULL,
    node_id         VARCHAR(100) NOT NULL,
    node_type       VARCHAR(50) NOT NULL,
    status          VARCHAR(30) NOT NULL
                    CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped', 'timeout')),
    attempt         INTEGER NOT NULL DEFAULT 1,
    input_payload   JSONB,
    output_payload  JSONB,
    error_message   TEXT,
    duration_ms     INTEGER,
    worker_id       VARCHAR(100),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, started_at)
) PARTITION BY RANGE (started_at);

CREATE INDEX idx_node_logs_execution_id ON node_logs(execution_id);
CREATE INDEX idx_node_logs_node_type ON node_logs(node_type);
CREATE INDEX idx_node_logs_status ON node_logs(status);

-- ============================================================
-- Initial partitions (current + next 2 months)
-- Cron job or script creates future partitions monthly
-- ============================================================
CREATE TABLE node_logs_2026_05 PARTITION OF node_logs
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');

CREATE TABLE node_logs_2026_06 PARTITION OF node_logs
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE TABLE node_logs_2026_07 PARTITION OF node_logs
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

-- Default partition catches any rows outside defined ranges
CREATE TABLE node_logs_default PARTITION OF node_logs DEFAULT;
