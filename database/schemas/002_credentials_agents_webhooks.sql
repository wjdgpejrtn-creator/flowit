-- 002_credentials_agents_webhooks.sql
-- Credential vault (BYTEA encrypted), agent registry, webhook endpoints

-- ============================================================
-- credentials
-- ============================================================
CREATE TABLE IF NOT EXISTS credentials (
    credential_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    name            VARCHAR(200) NOT NULL,
    credential_kind VARCHAR(50) NOT NULL
                    CHECK (credential_kind IN ('api_key', 'oauth_token', 'password', 'certificate', 'custom')),
    encrypted_data  BYTEA NOT NULL,
    metadata        JSONB DEFAULT '{}'::JSONB,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_credentials_updated_at
    BEFORE UPDATE ON credentials
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_credentials_user_id ON credentials(user_id);
CREATE INDEX IF NOT EXISTS idx_credentials_kind ON credentials(credential_kind);

-- ============================================================
-- agents
-- ============================================================
CREATE TABLE IF NOT EXISTS agents (
    agent_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    agent_type      VARCHAR(50) NOT NULL,
    public_key      TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'inactive'
                    CHECK (status IN ('active', 'inactive', 'error')),
    last_heartbeat  TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_agents_updated_at
    BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ============================================================
-- webhook_registry
-- ============================================================
CREATE TABLE IF NOT EXISTS webhook_registry (
    webhook_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    name            VARCHAR(200) NOT NULL,
    url             TEXT NOT NULL,
    secret_hash     VARCHAR(128),
    events          TEXT[] NOT NULL DEFAULT '{}',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_webhook_registry_updated_at
    BEFORE UPDATE ON webhook_registry
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_webhook_registry_user_id ON webhook_registry(user_id);
