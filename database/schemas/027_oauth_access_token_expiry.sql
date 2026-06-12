-- 027_oauth_access_token_expiry.sql
-- OAuth access token 만료시각 (#452 ② access token refresh): 연결/갱신 시점에 응답의
-- expires_in(초)으로부터 계산한 절대 만료시각(now + expires_in)을 영속화한다. 노드 실행 시
-- CredentialInjection._resolve_oauth가 이 값으로 만료 임박을 판정해 refresh_token으로 선제
-- 갱신한다. 없으면 google access token이 1시간 후 만료되어 워크플로우 실행이 401로 깨진다.
--
-- nullable — 기존 row(및 expires_in 미수신 경로)는 NULL. NULL은 만료시각 미상(레거시)으로
-- 취급되어 다음 주입 시 best-effort 갱신 후 backfill된다.
-- ADR-0011: 멱등 (IF NOT EXISTS) + schema_migrations 추적 대상. 008은 이미 적용된 파일이라
-- in-place 수정 대신 신규 ALTER 마이그레이션으로 분리한다 (024/026 선례 동일 패턴).

ALTER TABLE oauth_connections
    ADD COLUMN IF NOT EXISTS access_token_expires_at TIMESTAMPTZ;

COMMENT ON COLUMN oauth_connections.access_token_expires_at IS
    '#452 access token 절대 만료시각(연결/갱신 시 now+expires_in). NULL=만료 미상(레거시) → best-effort 갱신 대상.';
