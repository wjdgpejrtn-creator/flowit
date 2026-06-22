-- 016_storage_execution_quality.sql
-- New tables required by Storage ORM but missing from original DDL
-- node_results (REQ-007), tool_executions (REQ-005),
-- storage_objects (REQ-008), quality_gate_logs (REQ-006)

-- ============================================================
-- node_results (Spec: NodeResult entity from REQ-007)
-- ============================================================
CREATE TABLE IF NOT EXISTS node_results (
    node_result_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID NOT NULL REFERENCES executions(execution_id) ON DELETE CASCADE,
    node_instance_id UUID NOT NULL,
    status          VARCHAR(20) NOT NULL
                    CHECK (status IN ('succeeded', 'failed', 'cancelled', 'skipped')),
    output          JSONB NOT NULL DEFAULT '{}'::JSONB,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_node_results_execution_id ON node_results(execution_id);

-- ============================================================
-- tool_executions (Spec: ToolExecutionRecord from REQ-005)
-- ============================================================
CREATE TABLE IF NOT EXISTS tool_executions (
    tool_execution_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_name       VARCHAR(100) NOT NULL,
    input_data      JSONB NOT NULL,
    output_data     JSONB,
    status          VARCHAR(20) NOT NULL
                    CHECK (status IN ('success', 'failed', 'timeout')),
    duration_ms     INTEGER NOT NULL,
    error_message   TEXT,
    executed_at     TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tool_executions_tool_name ON tool_executions(tool_name);
CREATE INDEX IF NOT EXISTS idx_tool_executions_executed_at ON tool_executions(executed_at DESC);

-- ============================================================
-- storage_objects (Spec: StorageObject from REQ-008)
-- ============================================================
CREATE TABLE IF NOT EXISTS storage_objects (
    object_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bucket          VARCHAR(100) NOT NULL,
    key             VARCHAR(500) NOT NULL UNIQUE,
    size            BIGINT NOT NULL,
    content_type    VARCHAR(100) NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}'::JSONB,
    owner_id        UUID,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_storage_objects_owner_id ON storage_objects(owner_id);
CREATE INDEX IF NOT EXISTS idx_storage_objects_bucket ON storage_objects(bucket);

-- ============================================================
-- quality_gate_logs (Spec: QualityGateResult from REQ-006)
-- ============================================================
CREATE TABLE IF NOT EXISTS quality_gate_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    quality_status  VARCHAR(30) NOT NULL,
    metrics         JSONB NOT NULL,
    warnings        JSONB NOT NULL DEFAULT '[]'::JSONB,
    decision_reason TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_quality_gate_logs_document_id ON quality_gate_logs(document_id);
