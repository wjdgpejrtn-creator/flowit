-- 020_skills_marketplace_staging.sql
-- ADR-0020 ② skills_marketplace 3계층 게시 lifecycle 저장 — PR-2e DDL.
-- personal_skills / team_skills / company_skills 3계층 테이블 + skill_approvals(승인 감사).
--
-- ADR-0020 Q1: node_definition_id는 publish(PUBLISHED) 시점에만 채운다(Option B). 그 전까지
-- 노드 스펙은 staging_* 컬럼에 보관 → publish 시 NodeDefinition 생성·upsert 후 FK 연결.
-- ADR-0011: IF NOT EXISTS 멱등 + schema_migrations 추적 대상.
-- teams 테이블 부재로 team_skills.team_id는 FK 없이 UUID만 둔다 (ADR-0020 결정).

-- ── 1. personal_skills ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS personal_skills (
    skill_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id       UUID NOT NULL REFERENCES users(user_id),
    name                TEXT NOT NULL,
    description         TEXT NOT NULL,
    node_definition_id  UUID REFERENCES node_definitions(node_id),  -- publish 시 채움 (Q1)
    lifecycle_state     TEXT NOT NULL DEFAULT 'draft'
                          CHECK (lifecycle_state IN ('draft', 'review', 'approved', 'published', 'archived')),
    skill_document_uri  TEXT,
    embedding           VECTOR(768),
    workflow_id         UUID,  -- 연결 워크플로우 (workflows FK는 명세상 생략)
    tags                JSONB NOT NULL DEFAULT '[]'::jsonb,
    version             TEXT NOT NULL DEFAULT '0.1.0',
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- 노드 스펙 staging (publish 전 보관, ADR-0020 Q1 — NodeSpecStaging VO 평탄화)
    staging_category              TEXT,
    staging_input_schema          JSONB,
    staging_output_schema         JSONB,
    staging_risk_level            TEXT,
    staging_required_connections  JSONB,
    staging_service_type          TEXT,
    promoted_to_team_id UUID,  -- 팀 승격 완료 마킹 (검색 기본 제외 — 승격=복제)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_personal_skills_updated_at
    BEFORE UPDATE ON personal_skills
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_personal_skills_owner ON personal_skills(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_personal_skills_lifecycle ON personal_skills(lifecycle_state);
CREATE INDEX IF NOT EXISTS idx_personal_skills_node_def
    ON personal_skills(node_definition_id) WHERE node_definition_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_personal_skills_embedding
    ON personal_skills USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;

-- ── 2. team_skills ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS team_skills (
    skill_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL,  -- teams 테이블 부재로 FK 생략
    author_id           UUID NOT NULL REFERENCES users(user_id),
    name                TEXT NOT NULL,
    description         TEXT NOT NULL,
    node_definition_id  UUID REFERENCES node_definitions(node_id),
    lifecycle_state     TEXT NOT NULL DEFAULT 'draft'
                          CHECK (lifecycle_state IN ('draft', 'review', 'approved', 'published', 'archived')),
    skill_document_uri  TEXT,
    embedding           VECTOR(768),
    workflow_id         UUID,  -- 연결 워크플로우 (workflows FK는 명세상 생략)
    tags                JSONB NOT NULL DEFAULT '[]'::jsonb,
    version             TEXT NOT NULL DEFAULT '0.1.0',
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    staging_category              TEXT,
    staging_input_schema          JSONB,
    staging_output_schema         JSONB,
    staging_risk_level            TEXT,
    staging_required_connections  JSONB,
    staging_service_type          TEXT,
    promoted_from       UUID,  -- 원본 personal_skills.skill_id (승격 역추적)
    promoted_to_company_id UUID,  -- 전사 승격 완료 마킹
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_team_skills_updated_at
    BEFORE UPDATE ON team_skills
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_team_skills_team ON team_skills(team_id);
CREATE INDEX IF NOT EXISTS idx_team_skills_lifecycle ON team_skills(lifecycle_state);
CREATE INDEX IF NOT EXISTS idx_team_skills_node_def
    ON team_skills(node_definition_id) WHERE node_definition_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_team_skills_embedding
    ON team_skills USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;

-- ── 3. company_skills ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS company_skills (
    skill_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    author_id           UUID NOT NULL REFERENCES users(user_id),
    name                TEXT NOT NULL,
    description         TEXT NOT NULL,
    node_definition_id  UUID REFERENCES node_definitions(node_id),
    lifecycle_state     TEXT NOT NULL DEFAULT 'draft'
                          CHECK (lifecycle_state IN ('draft', 'review', 'approved', 'published', 'archived')),
    skill_document_uri  TEXT,
    embedding           VECTOR(768),
    workflow_id         UUID,  -- 연결 워크플로우 (workflows FK는 명세상 생략)
    tags                JSONB NOT NULL DEFAULT '[]'::jsonb,
    version             TEXT NOT NULL DEFAULT '0.1.0',
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    staging_category              TEXT,
    staging_input_schema          JSONB,
    staging_output_schema         JSONB,
    staging_risk_level            TEXT,
    staging_required_connections  JSONB,
    staging_service_type          TEXT,
    promoted_from       UUID,  -- 원본 team_skills.skill_id (승격 역추적)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE OR REPLACE TRIGGER set_company_skills_updated_at
    BEFORE UPDATE ON company_skills
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE INDEX IF NOT EXISTS idx_company_skills_lifecycle ON company_skills(lifecycle_state);
CREATE INDEX IF NOT EXISTS idx_company_skills_node_def
    ON company_skills(node_definition_id) WHERE node_definition_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_company_skills_embedding
    ON company_skills USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;

-- ── 4. skill_approvals (ApprovalWorkflow 감사 추적) ─────────────────────────
-- skill_id는 3계층 polymorphic 참조라 FK 생략 — scope 컬럼으로 어느 테이블인지 구분.
CREATE TABLE IF NOT EXISTS skill_approvals (
    approval_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_id      UUID NOT NULL,
    scope         TEXT NOT NULL CHECK (scope IN ('personal', 'team', 'company')),
    reviewer_id   UUID NOT NULL REFERENCES users(user_id),
    status        TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
    comment       TEXT,
    reviewed_at   TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skill_approvals_skill ON skill_approvals(skill_id, scope);

COMMENT ON TABLE personal_skills IS 'ADR-0020 ② — 개인 스킬 (Skill Builder 추출 DRAFT 시작점).';
COMMENT ON TABLE team_skills IS 'ADR-0020 ② — 팀 스킬 (personal 승격 결과).';
COMMENT ON TABLE company_skills IS 'ADR-0020 ② — 전사 스킬 (team 승격 결과 / seed 자동 PUBLISHED).';
COMMENT ON TABLE skill_approvals IS 'ADR-0020 ② — 스킬 게시 승인 감사 추적. skill_id는 scope별 polymorphic 참조.';
COMMENT ON COLUMN personal_skills.node_definition_id IS
    'ADR-0020 Q1: PUBLISHED 시점에만 채움. 그 전엔 staging_* 컬럼이 노드 스펙 보관.';
