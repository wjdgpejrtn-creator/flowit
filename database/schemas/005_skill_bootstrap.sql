-- 005_skill_bootstrap.sql
-- Skills marketplace model (Spec: REQ-008 Storage SkillModel)
-- Redesigned: condition/action/rationale → name/description marketplace

CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE skills (
    skill_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    description     TEXT NOT NULL,
    author_id       UUID NOT NULL REFERENCES users(user_id),
    lifecycle_state VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (lifecycle_state IN ('draft', 'pending_review', 'approved', 'rejected', 'archived')),
    workflow_id     UUID REFERENCES workflows(workflow_id),
    tags            TEXT[] NOT NULL DEFAULT '{}',
    version         VARCHAR(20) NOT NULL DEFAULT '0.1.0',
    metadata        JSONB NOT NULL DEFAULT '{}'::JSONB,
    embedding       vector(768),
    search_vector   TSVECTOR,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_skills_updated_at
    BEFORE UPDATE ON skills
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX idx_skills_embedding_hnsw ON skills
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_skills_search_vector_gin ON skills USING gin (search_vector);
CREATE INDEX idx_skills_author_id ON skills(author_id);
CREATE INDEX idx_skills_lifecycle_state ON skills(lifecycle_state);

-- ============================================================
-- skill_stats (aggregated metrics)
-- ============================================================
CREATE TABLE skill_stats (
    skill_id        UUID PRIMARY KEY REFERENCES skills(skill_id) ON DELETE CASCADE,
    use_count       INTEGER NOT NULL DEFAULT 0,
    avg_rating      NUMERIC(3, 2) NOT NULL DEFAULT 0.00,
    review_count    INTEGER NOT NULL DEFAULT 0,
    last_used_at    TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_skill_stats_updated_at
    BEFORE UPDATE ON skill_stats
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- ============================================================
-- skill_promotion_logs (lifecycle state audit trail)
-- ============================================================
CREATE TABLE skill_promotion_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id        UUID NOT NULL REFERENCES skills(skill_id) ON DELETE CASCADE,
    from_state      VARCHAR(20) NOT NULL,
    to_state        VARCHAR(20) NOT NULL,
    changed_by      UUID NOT NULL REFERENCES users(user_id),
    reason          TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_skill_promotion_logs_skill_id ON skill_promotion_logs(skill_id);
