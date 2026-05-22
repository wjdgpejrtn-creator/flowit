-- 019_node_definitions_scope.sql
-- ADR-0020 (i): node_definitions에 scope 격리 컬럼 추가.
-- owner_user_id/team_id 둘 다 NULL = company 전역 (기존 53종 비침습 — 데이터 마이그레이션 없음).
-- owner_user_id 값 = personal 스킬 소유자 / team_id 값 = team 스킬.
-- 검색 격리는 storage PgNodeDefinitionRepository.search_by_embedding의 viewer 필터가 사용한다.
--
-- ADR-0011: IF NOT EXISTS 멱등 + schema_migrations 추적 대상.
-- teams 테이블이 스키마에 부재해 team_id는 FK 없이 UUID만 둔다 (ADR-0020 결정).

ALTER TABLE node_definitions
    ADD COLUMN IF NOT EXISTS owner_user_id UUID REFERENCES users(user_id),
    ADD COLUMN IF NOT EXISTS team_id       UUID;

CREATE INDEX IF NOT EXISTS idx_node_definitions_owner
    ON node_definitions(owner_user_id)
    WHERE owner_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_node_definitions_team
    ON node_definitions(team_id)
    WHERE team_id IS NOT NULL;

COMMENT ON COLUMN node_definitions.owner_user_id IS
    'ADR-0020 (i) scope: NULL=company 전역(기존 53종) / 값=personal 스킬 소유자.';
COMMENT ON COLUMN node_definitions.team_id IS
    'ADR-0020 (i) scope: NULL=비team / 값=team 스킬. teams 테이블 부재로 FK 생략.';
