-- 011_session_storage.sql
-- Sessions (Spec: Session entity) + chat messages
-- Aligned: table name "sessions" (not "chat_sessions"), PK "session_id",
--          added device_info, removed kind/last_activity_at

CREATE TABLE sessions (
    session_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    session_hash    VARCHAR(64) NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    is_revoked      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    device_info     VARCHAR(200)
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_session_hash ON sessions(session_hash);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at)
    WHERE is_revoked = FALSE;

-- ============================================================
-- chat_messages (Spec: ConversationMessage entity)
-- ============================================================
CREATE TABLE chat_messages (
    message_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL
                    CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chat_messages_session_id ON chat_messages(session_id, created_at);
