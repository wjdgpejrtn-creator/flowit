-- 026_oauth_connection_account_display.sql
-- OAuth connection settings 목록 display 필드 (ADR-0027): connection을 매번 get_user_info로
-- 우회하지 않고, 연결 시점에 채워둔 안정 식별자(account_id)와 표시명(display_name)을 영속화한다.
--   - account_id   : 서비스측 안정 계정 식별자 (google=sub / slack=team_id)
--   - display_name : 사용자 노출용 라벨 (google=email / slack=workspace name)
--
-- 둘 다 nullable — 기존 row 및 식별자 미확보 경로는 NULL, 다음 connect/refresh 시 lazy backfill.
-- ADR-0011: 멱등 (IF NOT EXISTS) + schema_migrations 추적 대상. 008은 이미 적용된 파일이라
-- in-place 수정 대신 신규 ALTER 마이그레이션으로 분리한다 (024 선례 동일 패턴).

ALTER TABLE oauth_connections
    ADD COLUMN IF NOT EXISTS account_id   VARCHAR(255);

ALTER TABLE oauth_connections
    ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);

COMMENT ON COLUMN oauth_connections.account_id IS
    'ADR-0027 서비스측 안정 계정 식별자 (google=sub / slack=team_id). NULL=미확보 경로.';
COMMENT ON COLUMN oauth_connections.display_name IS
    'ADR-0027 settings 목록 표시명 (google=email / slack=workspace name). NULL=미확보 경로.';
