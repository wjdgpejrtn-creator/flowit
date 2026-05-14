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

COMMENT ON TABLE node_execution_states IS
    'Per-node execution state tracking for REQ-007 ExecutionRepositoryPort.update_node_state(). Composite PK (execution_id, node_instance_id) supports UPSERT on retry/state transition.';
