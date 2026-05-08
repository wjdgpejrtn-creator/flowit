-- 010_intent_feedback.sql
-- Intent classification logs and workflow feedback (append-only)

CREATE TABLE intent_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL,
    user_id         UUID NOT NULL REFERENCES users(user_id),
    user_message    TEXT NOT NULL,
    classified_intent VARCHAR(100) NOT NULL,
    confidence      NUMERIC(4, 3) NOT NULL,
    selected_nodes  JSONB DEFAULT '[]'::JSONB,
    metadata        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_intent_logs_session_id ON intent_logs(session_id);
CREATE INDEX idx_intent_logs_user_id ON intent_logs(user_id);
CREATE INDEX idx_intent_logs_created_at ON intent_logs(created_at DESC);

CREATE TABLE workflow_feedback (
    feedback_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES workflows(workflow_id),
    execution_id    UUID REFERENCES executions(execution_id),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    rating          INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment         TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_workflow_feedback_workflow_id ON workflow_feedback(workflow_id);
CREATE UNIQUE INDEX idx_workflow_feedback_execution_user
    ON workflow_feedback(execution_id, user_id);
