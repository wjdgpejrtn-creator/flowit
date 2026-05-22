-- 021_user_roles_expand.sql
-- User RBAC: team_manager / company_manager 역할 추가 (스킬 마켓플레이스 승인 인가).
-- 001_core.sql의 role CHECK는 ('User','Admin')만 허용 → team/company scope 승인용 역할 2종 추가.
-- 인가 정책: personal=owner / team=team_manager + department_id 매칭 / company=company_manager.
--
-- ADR-0011: 멱등 (DROP CONSTRAINT IF EXISTS → ADD) + schema_migrations 추적 대상.
-- CHECK는 001_core.sql에서 인라인 정의 → PG 자동 명명 'users_role_check'.

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;

ALTER TABLE users ADD CONSTRAINT users_role_check
    CHECK (role IN ('User', 'team_manager', 'company_manager', 'Admin'));
