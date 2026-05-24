# ADR-0020: Skills Builder 산출물 게시 lifecycle 게이트 + scope별 진입 (Option B)

- **Status**: Accepted (본 PR #132에서 Accept — #128은 Proposed 상태로 머지됨. GAP 2 (i) 확정, 2026-05-21)
- **Date**: 2026-05-21
- **Deciders**: @dhwang0803-glitch (조장, REQ-001/008/009) + @billionaireahreum (박아름, REQ-002/003/004 Skills Builder/013 skills_marketplace)
- **Tags**: area/skills_builder, area/skills_marketplace, area/nodes_graph, area/api_server, lifecycle, catalog

## Context

REQ-013 skills_marketplace는 5단계 게시 lifecycle(`DRAFT → REVIEW → APPROVED → PUBLISHED → ARCHIVED`)을 `SkillLifecycle` 서비스 + `MarketplaceSkill.lifecycle_state`로 정의하고, HITL 검토 게이트(`ApproveSkillUseCase` / `PublishSkillUseCase` / `ApprovalWorkflow`)도 갖췄다. 그러나 Skills Builder(REQ-004 `BuildFromSOPUseCase` / `BuildFromIndustryDefaultUseCase` / `BuildFromFunctionalDomainUseCase`)는 이 흐름을 우회한다.

2026-05-21 코드 검증으로 확인한 사실:

- (a) `MarketplaceSkill.node_definition_id` = **`UUID` Required** (Optional 아님).
- (b) `SkillRepository.search`는 `scope` / `include_promoted`만 받고 **`lifecycle_state` 필터가 없다** → DRAFT/REVIEW 스킬도 검색에 노출 가능.
- (c) team/company **직접 생성 경로가 없다** — `PromotionService`가 PERSONAL→TEAM→COMPANY 단방향 승격만 허용 (promotion-only).
- (d) `NodeDefinition`에 **scope/owner/lifecycle 필드가 없다**(현재) — 공유 카탈로그 개념. → 본 ADR에서 `owner_user_id`/`team_id`를 **Optional 추가**(lifecycle은 미포함). 시스템이 단일 인스턴스라 멀티테넌트(company/tenant) 컬럼은 불필요.
- (e) 시스템은 **단일 인스턴스** — User에 `company_id`/`tenant_id` 컬럼 없음(department만), scope는 `private/team/public` 사용자 단위, "company"=전사=전체 사용자(회사 아님). NodeDefinition은 이미 `service_type`/`embedding` 등 Optional 확장 필드 패턴.
- (+) `ApprovalWorkflow` 엔티티는 정의만 있고 **`ApproveSkillUseCase`에서 미사용** (reviewer_id를 파라미터로 받지만 레코드를 저장하지 않음) → 감사 추적 부재.

**결과**: `BuildFromSOPUseCase` 등이 `NodeDefinitionRepository.upsert()`로 노드를 카탈로그에 **즉시 라이브(=사실상 PUBLISHED)** 상태로 꽂는다. `MarketplaceSkill`(lifecycle_state)은 생성되지 않아 DRAFT/REVIEW/APPROVED를 전부 건너뛴다. 미검토 스킬이 Composer 노드 후보 검색을 오염시킬 수 있다.

## Decision

### 1. Option B — NodeDefinition은 PUBLISHED 시점에만 카탈로그 upsert

미검토 스킬이 카탈로그/검색을 오염시키지 않도록, `NodeDefinition`은 `lifecycle_state == PUBLISHED`가 될 때만 생성·upsert한다.

> **대안 A 기각**: 즉시 upsert + 검색에서 `lifecycle_state` 필터링. → `NodeDefinition`에 lifecycle을 추가하거나 nodes_graph 검색이 marketplace lifecycle을 알아야 해서 **nodes_graph ↔ marketplace 결합**이 생긴다. (d) NodeDefinition은 공유 카탈로그 개념을 유지해야 하므로 기각.

### 2. scope별 lifecycle 진입 분기

Skills Builder는 **personal 스킬만 직접 생성**한다 (Q3 promotion-only). team/company는 직접 생성하지 않고 personal을 승격(promote)한다:

| scope | 진입 경로 | lifecycle 진행 |
|-------|----------|----------------|
| personal | Skill Builder에서 직접 생성 (추출 → DRAFT) | DRAFT→REVIEW→APPROVED→PUBLISHED 전 과정 Skill Builder 페이지 in-place (owner=본인, self-review) |
| team / company | **Skill Builder 직접 생성 불가** — personal PUBLISHED를 `PromoteToTeam/Company`로 승격(DRAFT 복제, ADR-0019 promotion=복제) | Marketplace에서 리뷰어가 DRAFT→REVIEW→APPROVED→PUBLISHED 진행 |

UX 근거: personal은 본인이 쓸 스킬이라 Skill Builder에서 그 자리 완결(self-review). team/company는 promotion-only(Q3) — 검증된 personal 스킬을 승격하고, 타인(리뷰어) 검토가 필요하니 Marketplace가 거처. **Skill Builder 페이지의 scope 선택은 "personal 생성" 단일이며, team/company 노출은 Marketplace의 promote 흐름으로 분리**(초안의 3택 모델은 Q3 promotion-only로 정정됨).

### 3. Q1~Q8 확정 (2026-05-21 조장·박아름 합의)

| # | 결정 | 근거 |
|---|------|------|
| **Q1** DRAFT 노드스펙 거처 | `MarketplaceSkill.node_definition_id` → `UUID \| None`. 노드 스펙(`category`/`input_schema`/`output_schema`/`risk_level`/`required_connections`/`service_type`)을 **staging 필드**로 보관 → publish 시 `NodeDefinition` 생성. PR-2e DDL에 staging 컬럼 | (a)(d) — NodeDefinition은 PUBLISHED 전 존재 안 함 |
| **Q2** personal self-review | `SkillLifecycle` 4전이 모두 기록(audit), UI만 personal "검토→게시" 한 번으로 합침. self-approval 허용(owner=reviewer_id). **`ApprovalWorkflow` 실제 연결**(레코드 저장) | (+) 감사 추적 |
| **Q3** team/company 직접 생성 | **불가 — promotion-only 유지**. Skill Builder 직접 생성은 personal만, team/company는 `PromoteToTeam/Company`로 | (c) 직접 생성 경로 없음 + "promotion=복제" 일관 |
| **Q4** lifecycle use case 호출 위치 | `api_server`에 scope-aware lifecycle 라우트(submit/approve/publish) 신설 → skills_marketplace `ApproveSkill`/`PublishSkill` 호출 (Composition Root) | — |
| **Q5** 검색/가시성 | **(i) `NodeDefinition`에 `owner_user_id`/`team_id` Optional 추가** → 단일 카탈로그 + scope 필터. `NULL`=company 전역(기존 53종 포함) / `owner_user_id`=personal / `team_id`=team. 검색: `(owner IS NULL AND team IS NULL) OR owner=현재유저 OR team IN 내팀`. PUBLISHED만 upsert(lifecycle 게이트) 유지 | (e) 단일 인스턴스라 멀티테넌트 부담 0 + `NULL`=전역이라 기존 53종 비침습 |
| **Q6** batch 단위 | batch(SOP 1건=1 scope) 기본 + 스킬별 override는 후속 | — |
| **Q7** seed 경로 | seed(industry/functional)는 사전 큐레이션이라 **company scope 자동 PUBLISHED**(리뷰 생략). `source_type` 게이트(seed=자동 / sop=lifecycle) | 박아름 큐레이션 검증본 |
| **Q8** 추출 편집 wizard | **wizard 1차 채택** (2026-05-22 조장 입장 변경 — 기존 "one-shot 1차 / wizard 2차"에서 정정). 사용자가 추출된 노드 스펙(이름/설명/스키마)을 검토·수정 후 확정하는 wizard 구조로 간다. ③ `BuildFromXxx`를 **`extract_draft`(추출→`node_spec_staging` 반환) + `confirm`(편집 반영 → `CreateDraftSkillUseCase` DRAFT 저장)** 으로 분리 + frontend 다단계 검토 UI. lifecycle 게이트(§1)는 그대로 — wizard 확정 후 DRAFT부터 lifecycle 진행. ※ "personal in-place"(lifecycle 승인)와 wizard(추출 편집)는 별개 축이며 **둘 다 1차** | 사내 프로세스 안정 기업엔 불필요할 수 있으나, **스타트업·소규모는 wizard로 우리가 설계한 skill 구조를 확인하며 프로세스를 쌓아올리는 방향이 필요**(조장). one-shot은 검토 없는 확정이라 구조 학습/검증 기회 상실. staging(Q1)·`CreateDraftSkillUseCase`(②e) 기반이 이미 있어 wizard 백엔드 토대 확보 (2026-05-22 조장) |

### 4. 아키텍처 축 — NodeDefinition owner/scope Optional (단일 카탈로그)

> 초안의 "검색 이원화(company 카탈로그 / personal·team marketplace)"에서 **"단일 카탈로그 + Optional 격리"로 확정** (2026-05-21 조장 협의 + 코드 점검 (e)).

- `NodeDefinition`에 `owner_user_id: UUID | None` + `team_id: UUID | None` **Optional 추가** (lifecycle은 미포함 — PUBLISHED만 upsert로 게이트 유지).
- `NULL`=company 전역(기존 53종 + company 스킬) / `owner_user_id`=personal / `team_id`=team.
- 검색은 단일 `NodeDefinitionRepository.search`에 scope 필터: `(owner IS NULL AND team IS NULL) OR owner=현재유저 OR team IN 내팀`.

**안전성 (코드 점검 2026-05-21)**:
- **단일 인스턴스**(e) → 회사별 배포 설정 부담 없음.
- 기존 53종은 `NULL`=전역이라 **비침습**(현재 동작 유지). NodeDefinition이 이미 `service_type`/`embedding` Optional 확장 필드 패턴이라 owner/team Optional도 동일 — dataclass 기본값 `None` + DDL `nullable`.
- lifecycle은 NodeDefinition에 안 넣음 → "미검토 카탈로그 오염 방지"(Option B 본질)는 PUBLISHED만 upsert로 유지. (이 점에서 대안 A — lifecycle을 NodeDefinition에 넣는 것 — 과 다름. owner/scope는 멤버십 격리용일 뿐 lifecycle 결합 아님.)

### 5. 선행 코드 부채 / 신규 추가 (본 설계 전제)

1. **`NodeDefinition`에 `owner_user_id`/`team_id` Optional 추가** + `NodeDefinitionRepository.search`에 scope 필터 — (i) 핵심. 기존 53종=NULL=전역(비침습).
2. **`SkillRepository.search`에 `lifecycle_state` 필터 추가** — 현재 scope/include_promoted만. marketplace 스킬 목록에서 PUBLISHED만 노출하려면 필요.
3. **`ApprovalWorkflow` 실제 연결** — 현재 엔티티 정의만 있고 `ApproveSkillUseCase`가 reviewer_id를 받지만 레코드를 저장 안 함.

## Consequences

### 외부 모듈 영향

- **ai_agent** (REQ-004, 박아름) — `BuildFromXxx` 3종: `NodeDefinitionRepository.upsert()` 제거 → `MarketplaceSkill` DRAFT emit으로 변경. `ResultFrame.payload` 형태 변경. agent-skills-builder Modal 라우팅/응답 변경.
- **skills_marketplace** (REQ-013, 박아름) — `MarketplaceSkill.node_definition_id` Optional + 노드 스펙 staging 필드. `SkillRepository.search` lifecycle 필터. `ApproveSkillUseCase`에 ApprovalWorkflow 저장. publish 시 NodeDefinition 생성 로직. **(PR #150 후속, 2026-05-22)** `SubmitSkillUseCase`(DRAFT→REVIEW) 신설(PR #154). `Approve/PublishSkillUseCase` 인가 enforcement = **role base** (조장 role 인프라 PR #157 머지로 선결 완료). **박아름 후속 = `SkillApprovalPolicy`(domain/services)**: personal=소유자 본인(`actor==owner_user_id`) / team=`role=="team_manager"` AND `actor.department_id == skill.team_id`(department=team registry, `departments.sql` seed) / company=`role=="company_manager"`. ※`MarketplaceSkill.team_id` ↔ `department_id` 정합은 컨벤션(FK 부재) — 호출부가 team_id=department_id 보장.
- **auth / common_schemas** (REQ-002/012) — 위 인가 role base = **조장 PR #157 (merged 2026-05-24)로 일괄 처리**: `common_schemas.UserRole = Literal["User","team_manager","company_manager","Admin"]` **SSOT 신설** + `PermissionSource.role: UserRole` + `auth.domain.entities.user`는 re-export shim(기존 import 무변경) + `PermissionResolver` 매니저 정책(매니저는 워크플로우 `granted_scopes/risk_ceiling`을 User와 동일 — 승인은 별개 축) + `GrantUserRoleUseCase`(Admin-only, `PUT /auth/users/{id}/role`) + DB `021_user_roles_expand.sql` + TS 재생성. SSOT 통합은 박아름 리뷰 ① 제안 반영(2026-05-24 COMMENTED).
- **api_server** (REQ-009, 황대원) — scope-aware skill lifecycle 라우트(submit/approve/publish) 신설. submit 라우트는 `SubmitSkillUseCase`(PR #154) 머지 후 조립.
- **nodes_graph** (REQ-003, 박아름) — `NodeDefinition`에 `owner_user_id`/`team_id` Optional 추가 + `NodeDefinitionRepository.search`에 scope 필터(`(owner IS NULL AND team IS NULL) OR owner=현재유저 OR team IN 내팀`).
- **database** (REQ-001, 황대원) — PR-2e DDL에 staging 컬럼 + `node_definitions`에 `owner_user_id`/`team_id` **nullable** 컬럼(기존 53종=NULL=전역) + lifecycle_state 인덱스.
- **frontend** (REQ-010) — Skill Builder 페이지: **추출 결과 검토·수정 wizard(Q8, 1차)** + personal 생성 + in-place 검토(DRAFT→PUBLISHED) UI. 추출 → 사용자가 노드 스펙 확인/편집 → 확정 다단계 흐름. team/company는 별도 Marketplace promote 흐름(Q3 promotion-only — Skill Builder에 team/company 직접 생성 UI 없음).

### 긍정

- 미검토 스킬이 카탈로그/검색을 오염시키지 않음 (HITL 게이트 실효화).
- `NodeDefinition` 공유 카탈로그 개념 유지 (nodes_graph ↔ marketplace 결합 회피).
- personal in-place로 self-review wizard 부재 해소.
- promotion-only 유지로 모델 단순.

### 부정 / 제약

- `BuildFromXxx` 3종 + MarketplaceSkill 스키마 + NodeDefinition owner/team + api_server 라우트 + scope 필터 + frontend = 광범위 변경. 단계화 필요.
- 노드 스펙 staging ↔ NodeDefinition 이중 표현 (publish 시 변환).
- `NodeDefinition`에 owner/team Optional 추가로 기존 카탈로그 스키마 변경(단 NULL=전역이라 기존 53종 동작 비침습).

## Alternatives Considered

### A. 즉시 upsert + 검색에서 lifecycle 필터 (기각)
- NodeDefinition에 lifecycle/scope 추가 또는 nodes_graph 검색이 marketplace lifecycle 인지 → nodes_graph ↔ marketplace 결합. (d) 공유 카탈로그 개념 위반.

### B. NodeDefinition은 PUBLISHED만 카탈로그 + scope별 진입 (본 ADR 채택)
- ✅ 모듈 경계 깔끔, HITL 게이트 실효, 공유 카탈로그 유지.

## Related ADRs

- **ADR-0012** — database/storage/skills_marketplace 책임 분배 (MarketplaceSkill 3계층).
- **ADR-0017** — Skills Builder 산출물 NodeDefinition + SkillDocument 이중 저장. 본 ADR이 그 산출물의 게시 lifecycle을 정의 — ADR-0017의 "NodeDefinition 즉시 생성"을 "PUBLISHED 시점 생성"으로 **부분 대체**(ADR-0014→0018 선례). **Accepted 시 ADR-0017에 "ADR-0020으로 부분 대체" 마커 추가 + §2 표의 "NodeDefinition → skills_marketplace 테이블"을 실제대로 nodes_graph `node_definitions` 카탈로그로 정정** (NodeDefinition은 nodes_graph 소유, skills_marketplace 테이블은 MarketplaceSkill용).
- ADR-0018 — 노드 독립 실행 경로 (NodeDefinition 카탈로그 실행).

## References

- 설계 논의: 2026-05-21 조장 → 박아름 (Skills Builder 산출물 5단계 lifecycle 우회)
- 코드 검증: `marketplace_*_skill.py` (node_definition_id Required), `skill_lifecycle.py` (5전이), `skill_repository.py` (search lifecycle 필터 부재), `node_definition.py` (scope/lifecycle 필드 부재), `promotion_service.py` (promotion-only), `approve_skill_use_case.py` / `approval_workflow.py` (ApprovalWorkflow 미사용), `build_from_sop_use_case.py` (즉시 upsert)
