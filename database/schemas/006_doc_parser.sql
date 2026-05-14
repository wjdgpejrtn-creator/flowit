-- 006_doc_parser.sql
-- Document storage (Spec: DocumentBlock JSONB model) + chunked embeddings
-- Redesigned: normalized columns → JSONB blob (file_meta, parser_meta, blocks)

CREATE TABLE IF NOT EXISTS documents (
    document_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id     UUID,
    user_id         UUID,
    file_meta       JSONB NOT NULL,
    parser_meta     JSONB,
    blocks          JSONB NOT NULL DEFAULT '[]'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_workflow_id ON documents(workflow_id);
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);

-- ============================================================
-- document_chunks (Spec: Chunk entity with embedding)
-- ============================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_document_id  UUID NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_index         INTEGER NOT NULL,
    block_data          JSONB NOT NULL,
    importance_score    FLOAT,
    embedding           vector(768),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_parent ON document_chunks(parent_document_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding_hnsw ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
