-- 022_document_analysis_status.sql
-- Document 분석 상태 추적: analyze 비동기 태스크의 진행/실패 가시화.
-- 기존: blocks 비어 있음 = 분석 안 됨 / 채워 있음 = 분석 완료. 실패/진행중 구분 불가.
-- 변경: analysis_status enum + analysis_error TEXT + analyzed_at TIMESTAMPTZ.
--
-- 인가 정책 영향 없음 (owner-only 패턴 documents.user_id 기준 유지).
-- ADR-0011: 멱등 (IF NOT EXISTS) + schema_migrations 추적 대상.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'analysis_status_enum') THEN
        CREATE TYPE analysis_status_enum AS ENUM ('pending', 'running', 'completed', 'failed');
    END IF;
END
$$;

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS analysis_status analysis_status_enum NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS analysis_error TEXT,
    ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMPTZ;

-- 기존 row 보정: blocks가 비어있지 않으면 completed로 간주 (이전 분석 결과 보존).
UPDATE documents
SET analysis_status = 'completed',
    analyzed_at = COALESCE(analyzed_at, created_at)
WHERE analysis_status = 'pending'
  AND jsonb_array_length(blocks) > 0;

CREATE INDEX IF NOT EXISTS idx_documents_analysis_status ON documents(analysis_status);
