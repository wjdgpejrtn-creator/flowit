-- 007_langgraph_checkpoints.sql
-- LangGraph PostgresSaver compatible checkpoint tables (REQ-004/007)
-- These tables follow LangGraph's internal schema — do not modify column names

CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id               VARCHAR(200) NOT NULL,
    checkpoint_ns           VARCHAR(200) NOT NULL DEFAULT '',
    checkpoint_id           VARCHAR(200) NOT NULL,
    parent_checkpoint_id    VARCHAR(200),
    type                    VARCHAR(50),
    checkpoint              JSONB NOT NULL,
    metadata                JSONB DEFAULT '{}'::JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id       VARCHAR(200) NOT NULL,
    checkpoint_ns   VARCHAR(200) NOT NULL DEFAULT '',
    checkpoint_id   VARCHAR(200) NOT NULL,
    task_id         VARCHAR(200) NOT NULL,
    idx             INTEGER NOT NULL,
    channel         VARCHAR(200) NOT NULL,
    type            VARCHAR(50),
    value           JSONB,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
