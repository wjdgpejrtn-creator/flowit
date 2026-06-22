-- 017_node_execution_states.sql
-- Node-level execution state tracking (REQ-007 ExecutionRepositoryPort.update_node_state)
-- Spec: common_schemas.workflow.NodeExecutionState
--
-- ADR-0011: IF NOT EXISTS 멱등 + schema_migrations 추적 대상

CREATE TABLE IF NOT EXISTS node_execution_states (
    execution_id      UUID NOT NULL REFERENCES executions(execution_id) ON DELETE CASCADE,
    node_instance_id  UUID NOT NULL,
    status            VARCHAR(20) NOT NULL
                      CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'retrying', 'cancelled')),
    attempt           INTEGER NOT NULL DEFAULT 0,
    last_error        TEXT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (execution_id, node_instance_id)
);

CREATE INDEX IF NOT EXISTS idx_node_execution_states_execution_id
    ON node_execution_states(execution_id);

CREATE INDEX IF NOT EXISTS idx_node_execution_states_status
    ON node_execution_states(status);

-- BEFORE UPDATE trigger: 001_core.sql 정의 trigger_set_updated_at() 재사용
-- (UPSERT의 ON CONFLICT DO UPDATE 경로에서도 발동되어 updated_at 자동 갱신)
DROP TRIGGER IF EXISTS set_node_execution_states_updated_at ON node_execution_states;
CREATE TRIGGER set_node_execution_states_updated_at
    BEFORE UPDATE ON node_execution_states
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

COMMENT ON TABLE node_execution_states IS
    'Per-node execution LIVE state tracking for REQ-007 ExecutionRepositoryPort.update_node_state(). '
    'Composite PK (execution_id, node_instance_id) supports UPSERT on retry/state transition. '
    'Responsibility split vs 016 node_results: this table tracks transient live state during execution '
    '(status/attempt/last_error), whereas 016 node_results persists the final per-node outcome. '
    'executions.node_results JSONB column (001_core.sql) is the legacy aggregate snapshot.';
