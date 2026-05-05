-- 005_skill_bootstrap.sql
-- Skills with vector embeddings (BGE-M3 1024d) + HNSW index

CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================
-- skills
-- ============================================================
CREATE TABLE skills (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    condition       TEXT NOT NULL,
    action          TEXT NOT NULL,
    rationale       TEXT,
    status          VARCHAR(30) NOT NULL DEFAULT 'proposed'
                    CHECK (status IN ('proposed', 'pending_review', 'approved', 'rejected', 'needs_clarification')),
    version         VARCHAR(20) NOT NULL DEFAULT '1.0',
    category        VARCHAR(100),
    tags            JSONB DEFAULT '[]'::JSONB,
    industry        VARCHAR(100),
    embedding       vector(1024),
    scope           VARCHAR(20) NOT NULL DEFAULT 'private'
                    CHECK (scope IN ('private', 'team', 'public')),
    proposed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_skills_updated_at
    BEFORE UPDATE ON skills
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX idx_skills_user_id ON skills(user_id);
CREATE INDEX idx_skills_status ON skills(status);
CREATE INDEX idx_skills_scope ON skills(scope);
CREATE INDEX idx_skills_category ON skills(category);

-- HNSW cosine similarity index for vector search
CREATE INDEX idx_skills_embedding_hnsw ON skills
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search (Korean: 'simple' tokenizer + GIN)
CREATE INDEX idx_skills_fts ON skills
    USING gin (to_tsvector('simple', condition || ' ' || action));

-- ============================================================
-- skill_stats (aggregated metrics per skill)
-- ============================================================
CREATE TABLE skill_stats (
    skill_id        UUID PRIMARY KEY REFERENCES skills(id) ON DELETE CASCADE,
    usage_count     INTEGER NOT NULL DEFAULT 0,
    success_count   INTEGER NOT NULL DEFAULT 0,
    avg_rating      NUMERIC(3, 2) DEFAULT 0.00,
    last_used_at    TIMESTAMPTZ
);

-- ============================================================
-- skill_promotion_logs (status transition audit)
-- ============================================================
CREATE TABLE skill_promotion_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id        UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    from_status     VARCHAR(30) NOT NULL,
    to_status       VARCHAR(30) NOT NULL,
    changed_by      UUID NOT NULL REFERENCES users(id),
    reason          TEXT,
    changed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_skill_promotion_logs_skill_id ON skill_promotion_logs(skill_id);
