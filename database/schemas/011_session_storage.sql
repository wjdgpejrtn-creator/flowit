-- 011_session_storage.sql
-- Chat sessions and messages (REQ-002 session store + chat history)

-- ============================================================
-- chat_sessions
-- ============================================================
CREATE TABLE chat_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    session_hash    VARCHAR(128) NOT NULL,
    kind            VARCHAR(30) NOT NULL DEFAULT 'chat'
                    CHECK (kind IN ('chat', 'workflow_builder', 'skill_wizard')),
    is_revoked      BOOLEAN NOT NULL DEFAULT FALSE,
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE UNIQUE INDEX idx_chat_sessions_hash ON chat_sessions(session_hash)
    WHERE is_revoked = FALSE;
CREATE INDEX idx_chat_sessions_expires_at ON chat_sessions(expires_at)
    WHERE is_revoked = FALSE;

-- ============================================================
-- chat_messages
-- ============================================================
CREATE TABLE chat_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL
                    CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content         TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chat_messages_session_id ON chat_messages(session_id, created_at);
