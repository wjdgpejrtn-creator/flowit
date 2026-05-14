-- 012_agent_memory.sql
-- Agent long-term memory (Spec: MemoryEntry entity from REQ-004)
-- Simplified: removed scope, department_id, confidence, decay_factor,
--             embedding, last_used_at, usage_count (not in spec)

CREATE TABLE IF NOT EXISTS agent_memories (
    memory_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(user_id),
    source_session_id   UUID,
    memory_type         VARCHAR(50) NOT NULL,
    content             TEXT NOT NULL,
    metadata            JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_memories_user_id ON agent_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_memories_source_session ON agent_memories(source_session_id);
CREATE INDEX IF NOT EXISTS idx_agent_memories_memory_type ON agent_memories(memory_type);
