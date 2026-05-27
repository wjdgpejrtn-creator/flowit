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

### 승격 의미론 — 복제(원본 유지) (2026-05-20 조장 리뷰 #98 반영)

scope 승격(`PromoteToTeam`/`PromoteToCompany`)은 **이동(원본 비활성)이 아니라 복제(원본 유지)**로 정의한다.

| 항목 | 규칙 | 근거 |
|------|------|------|
| 원본 처리 | **유지** (삭제/비활성 안 함) — 이력 보존 | 이동 시 원본 이력 소실 |
| 양방향 추적 | 신규: `promoted_from` (← 원본) / 원본: `promoted_to_team_id`·`promoted_to_company_id` (→ 신규) | 조장: "원본 측 promoted_to 없음" 보완 |
| 검색 중복 방지 | `search(include_promoted=False)` 기본 — 승격 완료 원본(`promoted_to_* IS NOT NULL`) 제외 | 같은 스킬이 personal+team 중복 노출 방지 |
| **게시상태 재심사** | 승격 시 `lifecycle_state` 승계 안 함 → **DRAFT 리셋**. 넓은 scope는 재승인(`approve`→`publish`) 경유 | 노출 범위 확대 = 거버넌스 재심사 (ADR-0012 lifecycle 정책 정합) |

> 실제 검색 WHERE 필터(`promoted_to_* IS NULL`)는 `SkillRepository` storage 구현(조장 영역, PR-2d 후속) 시 적용. 본 모듈은 entity 필드 + Port 시그니처 + use case 마킹까지 제공.

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
| `MarketplacePersonalSkill` | `skill_id`, `owner_user_id`, `name`, `description`, `node_definition_id`(Optional, ADR-0020 Q1), `node_spec_staging`(Optional `NodeSpecStaging`), `lifecycle_state`, `skill_document_uri`, `embedding`, `workflow_id`, `tags`, `version`, `metadata`, `promoted_to_team_id`, `created_at`, `updated_at` | 개인 범위. `ai_agent.PersonalSkill`(메모리)과 도메인 다름 — `Marketplace` 접두사로 충돌 회피 (ADR-0012). `promoted_to_team_id` = 팀 승격 완료 마킹 (검색 기본 제외). `node_definition_id`는 PUBLISHED 시점에만 채움(그 전엔 `node_spec_staging` 보관, Option B) |
| `MarketplaceTeamSkill` | + `team_id`, `author_id`, `promoted_from` (원본 personal skill_id, 역추적), `promoted_to_company_id` (전사 승격 완료 마킹) | 팀 범위. PromoteToTeam으로 승격 |
| `MarketplaceCompanySkill` | + `author_id`, `promoted_from` (원본 team skill_id, 역추적) | 전사 범위(최종). PromoteToCompany로 승격 |
| `ApprovalWorkflow` | `approval_id`, `skill_id`, `scope`, `reviewer_id`, `status`, `comment`, `reviewed_at`, `created_at` | 게시 승인 워크플로우 (storage에서 이전). `ApproveSkillUseCase`가 `SkillRepository.save_approval`로 레코드 저장 (ADR-0020 + 감사 추적). `scope`(SkillScope)는 skill_approvals polymorphic 구분 + 감사 — use case가 채움(조장 A안) |
| `NodeSpecStaging` (VO) | `category`, `input_schema`, `output_schema`, `risk_level`, `required_connections`, `service_type` | publish 전 노드 스펙 임시 보관 (ADR-0020 Q1). PUBLISHED 시 이 staging + 스킬 메타 → `NodeDefinition` 생성 |
| `SkillDocument` | `skill_id`, `name`, `description`, `instructions`, `scripts`, `templates` | 스킬 지침서 (SKILL.md 레퍼런스). ADR-0017 이중 저장 중 GCS 측. **타입 SSOT = `common_schemas`(PR #111)** — skills_marketplace `domain/entities`는 재노출 shim (생산자 ai_agent + 저장자 skills_marketplace 공유, 2026-05-20 박아름 정정 후 PR #106 리뷰로 common_schemas 이동) |

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
| `SkillApprovalPolicy` | `authorize(*, scope, actor_user_id, actor_role, actor_department_id, skill_owner_user_id, skill_team_id) → None` | 승인/게시 actor 인가 (ADR-0020 위임2, role base). Admin=전체 / personal=`actor==owner` / team=`team_manager`+`actor.department_id==skill.team_id` / company=`company_manager`. 실패 시 `AuthorizationError`(fail-closed). primitive 입력 — `PermissionSource` 비의존(도메인 순수) |

### 2.4 domain/ports

| 포트(ABC) | 주요 메서드 | 구현 위치 |
|-----------|-------------|----------|
| `SkillRepository` | `save_personal/save_team/save_company`, `get_personal/get_team/get_company`, `search(query_embedding, scope, limit, include_promoted=False, lifecycle_state=None)`, `save_approval(approval)`, `list_personal_by_user(user_id, lifecycle_state?, limit=50, offset=0)`, `delete_personal(skill_id)` | `storage/repositories/` (ADR-0017 + 5/20 합의 — Port는 skills_marketplace, 구현은 storage). `include_promoted=False` 기본 = 승격 완료 원본(`promoted_to_*`) 제외. `lifecycle_state`(ADR-0020 (b)) = 게시 상태 필터(Composer는 PUBLISHED만). `save_approval` = ApprovalWorkflow 레코드 저장(ADR-0020 +). **`list_personal_by_user`/`delete_personal`(PR #192) = personal 미리보기/편집 UI 백엔드 — 소유자 목록(상태 필터·페이지네이션) + 단건 삭제, 인가/lifecycle은 use case** |
| `SkillDocumentStore` | `save(skill_id, document) → str (gs:// URI)`, `load(skill_id) → SkillDocument \| None`, `delete(skill_id)` | `storage/adapters/gcs_skill_document_store.py` (PR #160). `ObjectStoragePort` 조합 — production `GCSAdapter(SKILLS_MARKETPLACE_BUCKET)`, 테스트 `LocalStorageAdapter` swap. `save` 반환 URI를 호출부가 `skill_document_uri` 메타에 세팅(bucket 이름이 use case로 누수되지 않도록 어댑터 캡슐화). 키: `gs://{SKILLS_MARKETPLACE_BUCKET}/skills/{skill_id}/SKILL.md`. Port는 skills_marketplace 소유 (2026-05-20 정정). **`delete`(PR #192) = 개인 스킬 삭제 시 GCS SKILL.md 정리(2026-05-26 조장 결정, 멱등)** |

### 2.5 application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `CreateDraftSkillUseCase` | `owner_user_id, name, description, node_spec_staging, embedding?, skill_document_uri?, instructions? → UUID` | Skills Builder(③)가 추출 결과를 personal DRAFT로 생성 (ADR-0020 ②e). NodeDefinition 미생성(① 무관), 노드 스펙은 `node_spec_staging` 보관. `instructions`(SKILL.md 본문)가 주어지고 `SkillDocumentStore`가 주입돼 있으면 ADR-0017 이중 저장 — skill_id 생성 후 GCS save → 반환 URI를 `skill_document_uri`에 세팅(둘 중 하나라도 없으면 문서 미저장, 하위호환) |
| `PromoteToTeamUseCase` | `personal_skill_id, team_id → UUID` | 개인 → 팀 승격 (복제: 메타 승계 + 게시상태 DRAFT 재심사 + promoted_from 역추적 + 원본에 promoted_to_team_id 마킹) |
| `PromoteToCompanyUseCase` | `team_skill_id → UUID` | 팀 → 전사 승격 (복제: 동일 정책, 원본 team에 promoted_to_company_id 마킹) |
| `SearchSkillsUseCase` | `query_embedding, scope, limit → list[Skill]` | 하이브리드 검색 — ai_agent Composer 호출 (repo.search 위임, 승격 완료 원본 기본 제외) |
| `SubmitSkillUseCase` | `skill_id, scope` | 게시 검토 제출 DRAFT → REVIEW (ADR-0020 Q4, PR #150 위임). submit 라우트(REQ-009)가 조립 — 라우트 직접 전이 = Composition Root 위반이라 use case 선행 |
| `ApproveSkillUseCase` | `skill_id, scope, reviewer_id, approved, comment, *, actor_role, actor_department_id` | 게시 승인 REVIEW → APPROVED/DRAFT. reviewer=actor → `SkillApprovalPolicy`로 scope별 인가(ADR-0020 위임2) 후 전이 |
| `PublishSkillUseCase` | `skill_id, scope, *, actor_user_id, actor_role, actor_department_id` (생성자 +`node_def_repo`) | 게시 APPROVED → PUBLISHED. `SkillApprovalPolicy` 인가(위임2) 후 publish 시 `node_spec_staging` → `NodeDefinition` 생성·upsert + `node_definition_id` 연결 (ADR-0020 Option B/Q1, ②d). scope별 owner/team 격리. nodes_graph `NodeDefinitionRepository` 의존 |
| `ListUserPersonalSkillsUseCase` | `user_id, lifecycle_state?, limit=50, offset=0 → list[MarketplacePersonalSkill]` | 소유자 본인 personal 스킬 목록 — 미리보기 UI(REQ-013, 가원 요청). api_server `GET /skills/personal`가 현재 사용자 user_id 스코프로 호출 (PR #192) |
| `UpdatePersonalSkillUseCase` | `skill_id, actor_user_id, *, name?, description?, tags? → MarketplacePersonalSkill` | 개인 스킬 메타 수정 — 편집 UI. **owner만**(`AuthorizationError`) + **DRAFT만**(`ValidationError`), 빈값 거부·부분 수정·변경없으면 저장 skip. api_server `PUT /skills/personal/{id}` (PR #192) |
| `DeletePersonalSkillUseCase` | `skill_id, actor_user_id → None` (생성자 +`doc_store?`) | 개인 스킬 삭제 — **owner+DRAFT만**. `doc_store` 주입 시 GCS SKILL.md 먼저 정리(멱등)→DB row 삭제(orphan 방지). api_server `DELETE /skills/personal/{id}` (PR #192) |

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
| SkillRepository ABC 구현 (조장) | `PgMarketplaceSkillRepository` 3-scope 신규 (storage/repositories) | ✅ PR #147 |
| PR-2e | 3계층 schema 마이그레이션 (`020_skills_marketplace_staging.sql`) | ✅ PR #147 |
| storage/marketplace/ 원본 삭제 (조장) | 구 게시 도메인 복사본 8파일 삭제 + `test_skill_lifecycle` skills_marketplace로 이전 | ✅ PR #148 |
| personal 미리보기/편집 백엔드 (가원 요청) | Port `list_personal_by_user`/`delete_personal` + `SkillDocumentStore.delete` + UseCase 3(List/Update/Delete) | 🔵 PR #192 OPEN (조장 구현체 + api 라우트 4개 후속) |
