# REQ-013 Skills Marketplace — 구현 명세

- **담당자**: 박아름 (2026-05-20 이관, ADR-0012 §"REQ-013 후보" → 확정)
- **작성일**: 2026-05-20
- **참조**: [`ADR-0012`](../context/adr/ADR-0012-database-storage-module-boundary.md) (모듈 분리), [`ADR-0017`](../context/adr/ADR-0017-skills-builder-skill-document-dual-storage.md) (NodeDefinition + SkillDocument 이중 저장), `modules/skills_marketplace/README.md`

---

## 0. 개요

사내 Skills Marketplace 도메인. 외부 [SkillsMP](https://skillsmp.com/)와 동일한 역할(스킬 마켓플레이스)을 사내에서 구현하되 **외부 공유는 하지 않고 표준을 레퍼런스로만** 채택 (ADR-0017 §7). Skills Builder(REQ-004)가 생성한 스킬을 3계층(personal/team/company)으로 관리하고, Workflow Composer(REQ-004)가 사용자 의도와 유사한 스킬을 검색해 옵션 제시한다.

### 두 lifecycle 축 (옵션 A, 2026-05-20 조장 합의)

| 축 | value | 전이 service | 의미 |
|----|-------|-------------|------|
| `scope` (범위) | `SkillScope`: PERSONAL → TEAM → COMPANY | `PromotionService` | 공개 범위 승격 (단방향) |
| `lifecycle_state` (게시) | `SkillState`: draft → review → approved → published → archived | `SkillLifecycle` | 게시 상태 전이 |

한 스킬이 두 축을 동시에 가진다 (예: scope=team + lifecycle_state=published).

---

## 1. common_schemas에서 import할 클래스

| 클래스 | 소스 모듈 | 용도 |
|--------|-----------|------|
| `UtcDatetime` | `common_schemas.types` | entity created_at/updated_at 타입 |
| `ValidationError`, `NotFoundError` | `common_schemas.exceptions` | use case/service 예외 |

> 신규 도메인 타입(`MarketplacePersonalSkill` 등)은 skills_marketplace 모듈 내부 정의 (공유 타입 아님).

---

## 2. 이 모듈에서 구현할 클래스

### 2.1 domain/entities (3계층)

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `MarketplacePersonalSkill` | `skill_id`, `owner_user_id`, `name`, `description`, `node_definition_id`, `lifecycle_state`, `skill_document_uri`, `embedding`, `workflow_id`, `tags`, `version`, `metadata`, `created_at`, `updated_at` | 개인 범위. `ai_agent.PersonalSkill`(메모리)과 도메인 다름 — `Marketplace` 접두사로 충돌 회피 (ADR-0012) |
| `MarketplaceTeamSkill` | + `team_id`, `author_id`, `promoted_from` (personal skill_id) | 팀 범위. PromoteToTeam으로 승격 |
| `MarketplaceCompanySkill` | + `author_id`, `promoted_from` (team skill_id) | 전사 범위. PromoteToCompany로 승격 |
| `ApprovalWorkflow` | `approval_id`, `skill_id`, `reviewer_id`, `status`, `comment`, `reviewed_at`, `created_at` | 게시 승인 워크플로우 (storage에서 이전) |

### 2.2 domain/value_objects

| 클래스 | 설명 |
|--------|------|
| `SkillScope` | `str` Enum — PERSONAL/TEAM/COMPANY (범위 승격 단방향) |
| `SkillState` | `str` Enum — draft/review/approved/published/archived (게시 상태) |

### 2.3 domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `PromotionService` | `can_promote(current, target) → bool`, `next_scope(current) → SkillScope \| None` | 범위 승격 전이 규칙 (순수 로직) |
| `SkillLifecycle` | `can_transition(current, target) → bool`, `transition(current, target) → SkillState` | 게시 상태 전이 규칙 (순수 로직) |

### 2.4 domain/ports

| 포트(ABC) | 주요 메서드 | 구현 위치 |
|-----------|-------------|----------|
| `SkillRepository` | `save_personal/save_team/save_company`, `get_personal/get_team/get_company`, `search(query_embedding, scope, limit)` | `storage/repositories/` (ADR-0017 + 5/20 합의 — Port는 skills_marketplace, 구현은 storage) |

### 2.5 application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `PromoteToTeamUseCase` | `personal_skill_id, team_id → UUID` | 개인 → 팀 승격 (메타/게시상태 승계 + promoted_from) |
| `PromoteToCompanyUseCase` | `team_skill_id → UUID` | 팀 → 전사 승격 |
| `SearchSkillsUseCase` | `query_embedding, scope, limit → list[Skill]` | 하이브리드 검색 — ai_agent Composer 호출 (repo.search 위임) |
| `ApproveSkillUseCase` | `skill_id, scope, reviewer_id, approved` | 게시 승인 REVIEW → APPROVED/DRAFT |
| `PublishSkillUseCase` | `skill_id, scope` | 게시 APPROVED → PUBLISHED |

---

## 3. 의존 관계

```
Upstream (이 모듈이 의존):
  ├── common_schemas (REQ-012)   — UtcDatetime, exceptions
  ├── storage (REQ-008)          — SkillRepository ABC 구현체 (PR-2d 후속)
  └── nodes_graph (REQ-003)      — NodeDefinitionRepository (스킬 ↔ 노드 카탈로그 연결, PR-2d 후속)

Downstream (이 모듈에 의존):
  └── ai_agent (REQ-004)         — Workflow Composer가 SearchSkillsUseCase 호출
```

---

## 4. 산출물 이중 저장 (ADR-0017)

| 산출물 | 형식 | 저장 위치 |
|--------|------|----------|
| NodeDefinition (메타) | pydantic + JSON Schema | skills_marketplace 테이블 (PostgreSQL, PR-2e) |
| SkillDocument (지침서) | markdown frontmatter + body | GCS 버킷 (`skill_document_uri`) |

---

## 5. 구현 단계

| 단계 | 작업 | 상태 |
|------|------|------|
| 뼈대 (깊이 1) | 구조 + Port ABC + entity + README | ✅ PR #98 |
| PR-2d | use case 구현 + storage 게시 도메인 복사 + 정석 정정 | ✅ PR #98 흡수 |
| storage 정리 (조장) | storage/marketplace/ 원본 삭제 + pg_skill_repository → SkillRepository ABC 구현 | ⏳ |
| PR-2e | 3계층 schema 마이그레이션 (DB DDL — 카톡 협의) | ⏳ |
