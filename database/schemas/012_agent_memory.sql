-- 012_agent_memory.sql
-- Agent long-term memory with vector search + decay (REQ-004)

-- ============================================================
-- agent_memories
-- ============================================================
CREATE TABLE agent_memories (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(id),
    scope               VARCHAR(20) NOT NULL DEFAULT 'private'
                        CHECK (scope IN ('private', 'team', 'public')),
    department_id       UUID REFERENCES departments(id),
    memory_type         VARCHAR(50) NOT NULL
                        CHECK (memory_type IN (
                            'preference', 'correction', 'context', 'skill_usage', 'feedback'
                        )),
    content             TEXT NOT NULL,
    embedding           vector(1024),
    source_session_id   UUID,
    confidence          NUMERIC(4, 3) NOT NULL DEFAULT 1.000,
    decay_factor        NUMERIC(4, 3) NOT NULL DEFAULT 1.000,
    last_used_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    usage_count         INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_memories_user_id ON agent_memories(user_id);
CREATE INDEX idx_agent_memories_scope ON agent_memories(scope);
CREATE INDEX idx_agent_memories_memory_type ON agent_memories(memory_type);
CREATE INDEX idx_agent_memories_confidence ON agent_memories(confidence DESC);

-- HNSW cosine similarity index
CREATE INDEX idx_agent_memories_embedding_hnsw ON agent_memories
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
