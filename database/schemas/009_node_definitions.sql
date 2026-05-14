-- 009_node_definitions.sql
-- 54 MVP node types (Spec: NodeDefinition entity, NodeConfig shared type)
-- Aligned: name (not display_name), parameter_schema (not parameters),
--          risk_level + required_connections + service_type added, vector(768)

CREATE TABLE IF NOT EXISTS node_definitions (
    node_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_type           VARCHAR(100) NOT NULL UNIQUE,
    name                VARCHAR(200) NOT NULL,
    category            VARCHAR(50) NOT NULL
                        CHECK (category IN (
                            'trigger', 'action', 'condition', 'transform',
                            'ai', 'integration', 'utility', 'output'
                        )),
    version             VARCHAR(20) NOT NULL DEFAULT '1.0',
    input_schema        JSONB,
    output_schema       JSONB,
    parameter_schema    JSONB NOT NULL DEFAULT '{}'::JSONB,
    risk_level          VARCHAR(20) NOT NULL DEFAULT 'Low'
                        CHECK (risk_level IN ('Low', 'Medium', 'High', 'Restricted')),
    required_connections TEXT[] NOT NULL DEFAULT '{}',
    description         TEXT,
    is_mvp              BOOLEAN NOT NULL DEFAULT FALSE,
    service_type        VARCHAR(50),
    embedding           vector(768),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_node_definitions_updated_at
    BEFORE UPDATE ON node_definitions
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_node_definitions_category ON node_definitions(category);
CREATE INDEX IF NOT EXISTS idx_node_definitions_is_mvp ON node_definitions(is_mvp) WHERE is_mvp = TRUE;

CREATE INDEX IF NOT EXISTS idx_node_definitions_embedding_hnsw ON node_definitions
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
