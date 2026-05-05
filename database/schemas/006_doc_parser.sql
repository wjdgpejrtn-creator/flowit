-- 006_doc_parser.sql
-- Document parsing results (REQ-006)

-- ============================================================
-- documents (source files uploaded for parsing)
-- ============================================================
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id),
    workflow_id     UUID REFERENCES workflows(id),
    filename        VARCHAR(500) NOT NULL,
    mime_type       VARCHAR(100) NOT NULL,
    file_size_bytes BIGINT,
    storage_path    TEXT NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    metadata        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_user_id ON documents(user_id);
CREATE INDEX idx_documents_workflow_id ON documents(workflow_id);

-- ============================================================
-- document_blocks (chunked content after parsing)
-- ============================================================
CREATE TABLE document_blocks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    block_index     INTEGER NOT NULL,
    block_type      VARCHAR(30) NOT NULL
                    CHECK (block_type IN ('text', 'table', 'image', 'heading', 'list', 'code')),
    content         TEXT NOT NULL,
    embedding       vector(1024),
    metadata        JSONB DEFAULT '{}'::JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_document_blocks_document_id ON document_blocks(document_id);
CREATE INDEX idx_document_blocks_embedding_hnsw ON document_blocks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
