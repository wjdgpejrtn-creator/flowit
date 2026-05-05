-- 008_oauth_security.sql
-- OAuth connections (encrypted tokens) and security audit log

-- ============================================================
-- oauth_connections
-- ============================================================
CREATE TABLE oauth_connections (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(id),
    credential_id           UUID REFERENCES credentials(id),
    service                 VARCHAR(50) NOT NULL,
    access_token_encrypted  BYTEA,
    refresh_token_encrypted BYTEA,
    token_expires_at        TIMESTAMPTZ,
    scopes                  JSONB DEFAULT '[]'::JSONB,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_oauth_connections_updated_at
    BEFORE UPDATE ON oauth_connections
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX idx_oauth_connections_user_id ON oauth_connections(user_id);
CREATE INDEX idx_oauth_connections_service ON oauth_connections(service);
CREATE UNIQUE INDEX idx_oauth_connections_user_service_active
    ON oauth_connections(user_id, service) WHERE is_active = TRUE;

-- ============================================================
-- security_logs (append-only audit trail)
-- ============================================================
CREATE TABLE security_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    event_type      VARCHAR(100) NOT NULL,
    ip_address      INET,
    user_agent      TEXT,
    details         JSONB DEFAULT '{}'::JSONB,
    severity        VARCHAR(20) NOT NULL DEFAULT 'info'
                    CHECK (severity IN ('info', 'warning', 'critical')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_security_logs_user_id ON security_logs(user_id);
CREATE INDEX idx_security_logs_event_type ON security_logs(event_type);
CREATE INDEX idx_security_logs_severity ON security_logs(severity)
    WHERE severity IN ('warning', 'critical');
CREATE INDEX idx_security_logs_created_at ON security_logs(created_at DESC);
