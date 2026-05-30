-- 023_document_coverage.sql
-- 문서 파싱 커버리지 영속화: QualityGate가 산출한 ParseCoverage(total_pages/parsed_pages/
-- text·table·vision·failed blocks + warnings)를 documents row에 저장 → api/프론트가 분석
-- 결과로 노출. 기존엔 QualityGateResult.coverage가 계산만 되고 save_quality_log에서 드롭돼
-- 어디에도 보이지 않았다.
--
-- 인가 정책 영향 없음 (owner-only documents.user_id 기준 유지).
-- ADR-0011: 멱등 (IF NOT EXISTS) + schema_migrations 추적 대상.

ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS coverage JSONB;
