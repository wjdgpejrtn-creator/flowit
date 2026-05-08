-- 008_oauth_security.sql
-- OAuth connections (Spec: OAuthConnection entity) and security audit log

CREATE TABLE oauth_connections (
    oauth_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES users(user_id),
    service                 VARCHAR(50) NOT NULL,
    credential_id           UUID NOT NULL UNIQUE REFERENCES credentials(credential_id),
    access_token_encrypted  BYTEA NOT NULL,
    refresh_token_encrypted BYTEA,
    scopes                  TEXT[] NOT NULL DEFAULT '{}',
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    connected_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_refreshed_at       TIMESTAMPTZ
);

CREATE INDEX idx_oauth_connections_user_id ON oauth_connections(user_id);
CREATE INDEX idx_oauth_connections_service ON oauth_connections(service);
CREATE UNIQUE INDEX idx_oauth_connections_user_service_active
    ON oauth_connections(user_id, service) WHERE is_active = TRUE;

-- ============================================================
-- security_logs (append-only audit trail)
-- ============================================================
CREATE TABLE security_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(user_id),
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
