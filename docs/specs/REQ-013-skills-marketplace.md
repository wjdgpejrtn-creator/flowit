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
| `ListReviewQueueUseCase` | `actor_role, scope=PERSONAL, limit=50, offset=0 → list[Marketplace{Personal\|Team\|Company}Skill]` | 관리자 리뷰 큐 — REVIEW 상태 스킬 모아보기. **Admin only**(`AuthorizationError`, cross-user/team 조회). `scope=personal`=`list_personal_by_state(REVIEW)`(owner 리뷰 요청), `scope=team\|company`=`list_by_scope(scope, REVIEW)`(승격 요청분). api_server `GET /skills/review-queue?scope=` (PR #289 personal + PR #301 scope 확장). `scope`는 하위호환 default=personal |
| `GetPersonalSkillUseCase` | `skill_id, actor_user_id → MarketplacePersonalSkill` | 개인 스킬 단건 조회 — 미리보기 UI. **owner만**(`AuthorizationError`). lifecycle 제약 없음 — DRAFT 외(REVIEW/APPROVED/PUBLISHED) 상태도 owner면 조회 가능(조회 가능 조건 ≠ 편집 가능 조건). api_server `GET /skills/personal/{id}`가 PermissionSource.user_id를 actor로 위임 (PR #195, 조장 — Update/Delete의 owner-검사 패턴을 라우터가 들고 있지 않도록 use case로 분리) |
| `UpdatePersonalSkillUseCase` | `skill_id, actor_user_id, *, name?, description?, tags?, instructions? → MarketplacePersonalSkill` (생성자 +`doc_store?`) | 개인 스킬 수정 — 편집 UI. **owner만**(`AuthorizationError`), 빈값 거부·부분 수정·변경없으면 저장 skip. **lifecycle 제약 없음 — owner면 게시(PUBLISHED) 스킬도 수정**(2026-06-02 황대원 결정, 상세 페이지 편집 UX. 기존 DRAFT-only(2026-05-26 박아름)에서 완화, 박아름 위임 OK). `instructions`(SKILL.md 본문) 수신 + `doc_store` 주입 시 SkillDocument를 GCS에 재저장(ADR-0017). ⚠️ description/instructions 수정해도 **검색 임베딩(768d) 미재계산** — Composer 검색 랭킹 stale, 재생성은 후속(아래 임베딩 후속 항목). api_server `PUT /skills/personal/{id}` (PR #192, instructions·정책완화 PR #329) |
| `GetPersonalSkillDocumentUseCase` | `skill_id, actor_user_id → SkillDocument` (생성자 +`doc_store`) | 개인 스킬 지침서(SKILL.md) 본문 조회 — 상세 페이지 우측 패널. **owner만**(`AuthorizationError`), **lifecycle 무관**(미게시 DRAFT 본문도 owner 미리보기/편집). GCS `load`, 본문 없으면 `NotFoundError`(→404 graceful). 마켓플레이스 `GetMarketplaceSkillDocumentUseCase`(PUBLISHED만, 공개 browse)와 신뢰 경계 다름. api_server `GET /skills/personal/{id}/document` (PR #329) |
| `DeletePersonalSkillUseCase` | `skill_id, actor_user_id → None` (생성자 +`doc_store?`) | 개인 스킬 삭제 — **owner+DRAFT만**(Update와 달리 삭제는 DRAFT 제약 유지). `doc_store` 주입 시 GCS SKILL.md 먼저 정리(멱등)→DB row 삭제(orphan 방지). api_server `DELETE /skills/personal/{id}` (PR #192) |

> **승격 요청 엔드포인트 (PR #301).** `POST /api/v1/skills/{id}/promote {from_scope}` — personal→team(`PromoteToTeam`, team_id=요청자 `department_id`, owner 선검증) / team→company(`PromoteToCompany`). 승격 use case는 상위 scope를 **DRAFT로 복제**하므로, 라우트가 이어서 `SubmitSkillUseCase`로 **REVIEW** 전이해 관리자 리뷰 큐에 노출시킨다(promote+submit은 같은 request 세션 = 단일 트랜잭션, submit 실패 시 함께 롤백 → orphan 없음). 이후 관리자 `approve`→`publish`. 승격 use case 자체는 무변경 — 노출/조립만 api_server 추가. team→company 승격의 actor 인가는 후속(승인 단계 `SkillApprovalPolicy` manager 게이트로 최종 보호).

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
| personal 미리보기/편집 백엔드 (가원 요청) | Port `list_personal_by_user`/`delete_personal` + `SkillDocumentStore.delete` + UseCase 3(List/Update/Delete) | ✅ PR #192 |
| personal 미리보기/편집 storage 구현체 (조장) | `PgMarketplaceSkillRepository.list_personal_by_user`/`delete_personal` + `GcsSkillDocumentStore.delete` + `GCSAdapter.delete` 정규화 | ✅ PR #193 |
| personal 미리보기/편집 api_server 라우트 (조장) | 4 엔드포인트(`GET /personal`, `GET/PUT/DELETE /personal/{id}`) + `PersonalSkillResponse` 슬림 DTO + `GetPersonalSkillUseCase`(조장 신설, owner-검사 라우터 분산 방지) | 🔵 PR #195 OPEN |
| 런타임 주입 코어 (조장, 박아름 위임) | `NodeInstance.skill_id` + execution_engine 실행 시 instructions를 LLM 노드 system에 주입 | ✅ PR #265 머지 (worker `00025-hw7`) |
| 상세 페이지 지침서 + personal 본문/게시 수정 (조장, 박아름 위임) | `GetPersonalSkillDocumentUseCase` + `Update`에 instructions·게시 스킬 허용 + `GET /personal/{id}/document` + 프론트 마크다운 우측 패널(`MarkdownView`) | 🔵 PR #329 OPEN |
| ⚠️ 임베딩 재생성 후속 (미착수) | 게시 personal 스킬의 description/instructions 수정 시 검색 임베딩(768d) 재계산 — `PublishSkillUseCase`의 embedder 경로 재사용. 미구현 시 Composer 검색 랭킹이 옛 본문 기준(런타임 주입은 `load()`로 최신이라 무영향) | ⬜ TODO |
| two-shot 1차 SSE 계약 (조장, 위임) | `SkillSelectionFrame`+`SkillOption`(common_schemas transport, v0.18.0) | ✅ PR #267 OPEN |
| two-shot 바인딩 생산자 Phase 2 (조장, 위임) | `ComposerStateStore`+`GCSComposerStateStore` + composer round 분기/3 신규 노드 + payload relay 4-hop + `/slot` SSE (§6.5) | 🔵 진행 중 (feature/req-013-composer-two-shot) |
| two-shot frontend Phase 3 (가원) | `skill_selection` 프레임 소비 + 옵션 UI + `/slot` 트리거 | ⬜ 대기 |

## 6. 런타임 주입 — 워크플로우 실행 시 SkillDocument → LLM 노드 (REQ-013 코어, PR #265)

Skill의 본질 = **워크플로우 LLM 노드 실행 시 프롬프트로 주입되는 도메인 전문가 지침서**(Anthropic SKILL.md 패러다임). 생성 단계의 검색(`SearchSkillsUseCase`, Composer)과 별개로, **실행 단계에서 바인딩된 SkillDocument의 `instructions`를 LLM 노드 `system` 프롬프트에 주입**하는 계약이다.

### 6.1 바인딩
- `common_schemas.NodeInstance.skill_id: Optional[UUID]` — 노드에 바인딩된 스킬(`credential_id`와 동일한 "노드별 외부 참조" 패턴, default None).
- 바인딩 **소스**(노드에 skill_id를 박는 생산자) = Composer two-shot HITL 스킬 선택(**후속 PR**). 본 코어는 **소비**(주입)만 담당.

### 6.2 주입 (execution_engine)
- `CatalogNodeExecutor`가 노드 실행 시: `node.skill_id`가 있고 LLM 노드(`category=="ai"` **AND** input_schema에 `system` 필드 보유)이면 `SkillDocumentStore.load(skill_id)` → `SkillDocument.instructions`를 `system`에 병합(기존 system 있으면 지침서 prepend + `---` 구분자).
- instructions SSOT = GCS(`skills/{skill_id}/SKILL.md`), `load(skill_id)`로 로드(scope 불필요).
- **degrade 안전**: store 미배선 / load None·예외 / 비-LLM 노드 → 무주입 진행(skill은 선택적 보강이라 RuntimeError 없음). 기존 워크플로우(skill_id 없음) 완전 역호환.
- ⚠️ **카탈로그 불변식 (게이트 정확성 의존)**: 주입 게이트는 *"LLM(ai 모듈)을 호출하는 노드 ⇒ `category=="ai"`"* 규약에 묶인다. 현재 LLM 호출 노드는 `anthropic_chat`/`gemma_chat` 2개뿐이고 둘 다 충족(누락 0). **향후 LLM을 내부 호출하면서 `output`/`transform` 등으로 태깅된 편의 노드를 추가하면 스킬 주입에서 silent 누락**(degrade라 무에러)되므로, 그런 노드는 `category="ai"` 유지 또는 게이트 판별식 동반 갱신이 필수다.

### 6.3 의존성 / 인프라
- execution_engine → `skills_marketplace.domain.ports.SkillDocumentStore`(port, `TYPE_CHECKING` import — DIP). 구현 `GcsSkillDocumentStore`(storage/adapters)는 container(composition root)에서 조립.
- worker SA는 `skills_marketplace_bucket`에 **reader** 권한 필요(`load()` read-only). 미부여 시 403 → 무주입 silent degrade.

### 6.5 바인딩 생산자 — Composer two-shot HITL 스킬 선택 (REQ-013, Phase 2, 황대원/위임)
§6.1의 "바인딩 소스". Composer를 one-shot → **two-shot**으로 전환해 사용자가 선택한 `skill_id`를 워크플로우 LLM 노드에 박는다. **접근 = 세션 라운드트립**(composer는 stateless Modal·checkpointer 없음이라 interrupt 부적합 — execution_engine pause/resume 아날로그).

- **흐름**:
  - **[1차]** `compress→security→intent→search_nodes→suggest_skill_select`: 스킬 검색(지침서형/노드형 무관, `skill_id`만 있으면 옵션화) → `SkillSelectionFrame`(common_schemas `transport/sse.py`, PR #267) emit → 그래프 상태(`draft_spec`/`node_candidates`/`intent`)를 GCS 영속 → **END**(draft 미생성).
  - **[선택]** frontend가 옵션 렌더 → `POST /api/v1/agents/sessions/{id}/slot {skill_id, field_name}`.
  - **[2차]** `/slot` → orchestrator → composer `resume`: GCS 복원 + `selected_skill_id` 주입 → `draft_workflow→bind_skill→validate→qa→promote→save→confirm→memory→END`.
- **신규 노드 (composer_graph)**: `suggest_skill_select`(1차 종단), `resume`(2차 진입, 복원 실패 시 `E_SESSION_EXPIRED`), `bind_skill`(draft 후 결정론적 후처리 — 첫 LLM 노드(`category=="ai"`)에 `model_copy(skill_id=…)`. 0개→skip+경고, 복수→첫 노드 MVP 휴리스틱). round 분기는 `set_conditional_entry_point`(round=2→resume, else→compress).
- **drafter_service 무변경** — 바인딩은 composer 후처리(소유 모듈 정혜님 충돌 최소화).
- **상태 영속**: `ComposerStateStore`(ai_agent `domain/ports`, `save/load/delete_state: dict`) + `GCSComposerStateStore`(`adapters/memory`, `composer_state/{session_id}.json`, `GCS_SESSION_BUCKET`). 2차 성공 종료 시 `delete_state`(멱등).
- **payload relay 4-hop**(round/selected_skill_id 보존): api_server `/slot`(round=2 payload) → orchestrator main → supervisor(`_relay_stream` payload + round=2 직행 relay, intent 재분석 생략) → composer main → `composer_graph.stream(round, selected_skill_id)`. selected_skill_id는 JSON relay로 str 도착 → composer 경계에서 UUID 강제.
- **one-shot 폴백(회귀 보존)**: `skill_search`/`embedder`/`composer_state_store` 미주입 또는 후보 0건이면 `suggest_skill_select`가 한 라운드 안에서 draft로 진행(중단 없음).
- **레거시 정리**: 기존 `_suggest_skill_node`(스킬을 `SlotFillQuestionFrame.question` 문자열로 욱여넣던 경로)와 `_use_suggested_skill_node`는 현 `_build` 미등록 dead code — 본 PR은 신규 노드를 **가산**하고 dead code는 보존(제거는 정혜님 협의 + agent tool-loop 정리와 함께). PR #267 리뷰 LOW #2 후속.

### 6.4 후속 설계 — ②"워크플로우 작성 가이드"형 스킬 (박아름 복귀 후)
본 코어(§6)는 **①노드 바인딩 지침서 → 실행 시 LLM 노드 주입**만 다룬다. 스킬에는 개념적으로 **②"워크플로우를 *어떻게 조립*하는지"에 대한 작성 가이드**도 존재할 수 있고, 이는 런타임 노드가 아니라 **생성 단계 Composer(workflow agent)의 system 프롬프트에 주입**돼야 한다(①과 대칭). 현 모델 미지원 — (a) `SkillDocument`에 종류(`kind`) 판별자 없음, (b) 스킬이 `node_definition_id` 중심(노드=스킬)이라 노드 없는 순수 작성 가이드 표현 불가, (c) `_suggest_skill_node`가 `node_definition_id is None` 스킬을 skip해 surfacing 불가, (d) Composer가 `SkillDocument.instructions`를 자기 프롬프트에 안 읽음(name/description만 사용). → ② 지원 시 스킬 `kind` 판별자 + Composer 생성 시 instructions를 workflow-agent system에 병합하는 대칭 주입점 필요. **REQ-013 owner(박아름) 복귀 후 설계 결정 사안.**
