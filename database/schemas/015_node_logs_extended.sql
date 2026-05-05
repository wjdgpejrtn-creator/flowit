-- 015_node_logs_extended.sql
-- Extend node_logs with retry, tool, and token usage columns

ALTER TABLE node_logs
    ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tool_name VARCHAR(100),
    ADD COLUMN IF NOT EXISTS tool_version VARCHAR(20),
    ADD COLUMN IF NOT EXISTS tokens_input INTEGER,
    ADD COLUMN IF NOT EXISTS tokens_output INTEGER,
    ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(10, 6);

-- Index for LLM cost tracking
CREATE INDEX IF NOT EXISTS idx_node_logs_tool_name ON node_logs(tool_name)
    WHERE tool_name IS NOT NULL;
