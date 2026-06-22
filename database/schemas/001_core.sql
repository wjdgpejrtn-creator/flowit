-- 001_core.sql: extensions, trigger helper, departments, users, workflows, executions

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- departments
-- ============================================================
CREATE TABLE IF NOT EXISTS departments (
    department_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(100) NOT NULL UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- users
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) NOT NULL UNIQUE,
    name            VARCHAR(100) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'User'
                    CHECK (role IN ('User', 'Admin')),
    department      VARCHAR(100),
    department_id   UUID REFERENCES departments(department_id),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_department_id ON users(department_id);

-- ============================================================
-- workflows  (Spec: WorkflowSchema + DB ownership)
-- ============================================================
CREATE TABLE IF NOT EXISTS workflows (
    workflow_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(user_id),
    name                    VARCHAR(200) NOT NULL,
    description             TEXT,
    scope                   VARCHAR(20) NOT NULL DEFAULT 'private'
                            CHECK (scope IN ('private', 'team', 'public')),
    is_draft                BOOLEAN NOT NULL DEFAULT TRUE,
    draft_spec              JSONB,
    nodes                   JSONB NOT NULL DEFAULT '[]'::JSONB,
    connections             JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_via_session_id  UUID,
    version                 INTEGER NOT NULL DEFAULT 1,
    sha256                  VARCHAR(64),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_workflows_updated_at
    BEFORE UPDATE ON workflows
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_workflows_user_id ON workflows(user_id);
CREATE INDEX IF NOT EXISTS idx_workflows_scope ON workflows(scope);
CREATE INDEX IF NOT EXISTS idx_workflows_is_draft ON workflows(is_draft) WHERE is_draft = TRUE;

-- ============================================================
-- executions  (Spec: ExecutionResult + ExecutionContext.user_id)
-- ============================================================
CREATE TABLE IF NOT EXISTS executions (
    execution_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID NOT NULL REFERENCES workflows(workflow_id),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    status          VARCHAR(30) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'paused', 'completed', 'failed', 'cancelled')),
    node_results    JSONB NOT NULL DEFAULT '{}'::JSONB,
    error           TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_executions_workflow_id ON executions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_executions_user_id ON executions(user_id);
CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
