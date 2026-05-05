-- 009_node_definitions.sql
-- 54 MVP node types with vector embeddings for semantic search (REQ-003)

-- ============================================================
-- node_definitions
-- ============================================================
CREATE TABLE node_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_type       VARCHAR(100) NOT NULL UNIQUE,
    category        VARCHAR(50) NOT NULL
                    CHECK (category IN (
                        'trigger', 'action', 'condition', 'transform',
                        'ai', 'integration', 'utility', 'output'
                    )),
    display_name    VARCHAR(200) NOT NULL,
    description     TEXT,
    parameters      JSONB NOT NULL DEFAULT '{}'::JSONB,
    input_schema    JSONB,
    output_schema   JSONB,
    embedding       vector(1024),
    is_mvp          BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    version         VARCHAR(20) NOT NULL DEFAULT '1.0',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_node_definitions_updated_at
    BEFORE UPDATE ON node_definitions
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX idx_node_definitions_category ON node_definitions(category);
CREATE INDEX idx_node_definitions_is_mvp ON node_definitions(is_mvp) WHERE is_mvp = TRUE;

-- HNSW cosine similarity index for semantic node search
CREATE INDEX idx_node_definitions_embedding_hnsw ON node_definitions
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Full-text search
CREATE INDEX idx_node_definitions_fts ON node_definitions
    USING gin (to_tsvector('simple', display_name || ' ' || COALESCE(description, '')));
