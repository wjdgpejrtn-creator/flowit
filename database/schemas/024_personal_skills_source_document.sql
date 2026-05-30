-- 024_personal_skills_source_document.sql
-- 문서→스킬빌더 핸드오프 association 영속화 (REQ-010): 개인 스킬이 어느 문서를 기반으로
-- 만들어졌는지 documents(document_id)를 가리킨다. 문서→빌더 진입 시 채워지며, 직접 진입/
-- seed 경로에선 NULL.
--
-- ON DELETE SET NULL: 기반 문서가 삭제돼도 스킬 자체는 유지(association만 끊김). personal_skills
-- 만 대상 — team/company는 personal 승격 복제본이라 문서 association을 가지지 않는다.
-- ADR-0011: 멱등 (IF NOT EXISTS) + schema_migrations 추적 대상.

ALTER TABLE personal_skills
    ADD COLUMN IF NOT EXISTS source_document_id UUID REFERENCES documents(document_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_personal_skills_source_document
    ON personal_skills(source_document_id) WHERE source_document_id IS NOT NULL;

COMMENT ON COLUMN personal_skills.source_document_id IS
    'REQ-010 문서→빌더 핸드오프: 이 스킬의 기반 문서(documents.document_id). NULL=직접 진입/seed.';
