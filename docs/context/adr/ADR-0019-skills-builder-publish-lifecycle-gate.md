# ADR-0019: Skills Builder 산출물 게시 lifecycle 게이트 + scope별 진입 (Option B)

- **Status**: Proposed
- **Date**: 2026-05-21
- **Deciders**: @dhwang0803-glitch (조장, REQ-001/008/009) + @billionaireahreum (박아름, REQ-002/003/004 Skills Builder/013 skills_marketplace)
- **Tags**: area/skills_builder, area/skills_marketplace, area/nodes_graph, area/api_server, lifecycle, catalog

## Context

REQ-013 skills_marketplace는 5단계 게시 lifecycle(`DRAFT → REVIEW → APPROVED → PUBLISHED → ARCHIVED`)을 `SkillLifecycle` 서비스 + `MarketplaceSkill.lifecycle_state`로 정의하고, HITL 검토 게이트(`ApproveSkillUseCase` / `PublishSkillUseCase` / `ApprovalWorkflow`)도 갖췄다. 그러나 Skills Builder(REQ-004 `BuildFromSOPUseCase` / `BuildFromIndustryDefaultUseCase` / `BuildFromFunctionalDomainUseCase`)는 이 흐름을 우회한다.

2026-05-21 코드 검증으로 확인한 사실:

- (a) `MarketplaceSkill.node_definition_id` = **`UUID` Required** (Optional 아님).
- (b) `SkillRepository.search`는 `scope` / `include_promoted`만 받고 **`lifecycle_state` 필터가 없다** → DRAFT/REVIEW 스킬도 검색에 노출 가능.
- (c) team/company **직접 생성 경로가 없다** — `PromotionService`가 PERSONAL→TEAM→COMPANY 단방향 승격만 허용 (promotion-only).
- (d) `NodeDefinition`에 **scope/owner/lifecycle 필드가 없다** — 모든 사용자가 보는 공유 카탈로그 개념.
- (+) `ApprovalWorkflow` 엔티티는 정의만 있고 **`ApproveSkillUseCase`에서 미사용** (reviewer_id를 파라미터로 받지만 레코드를 저장하지 않음) → 감사 추적 부재.

**결과**: `BuildFromSOPUseCase` 등이 `NodeDefinitionRepository.upsert()`로 노드를 카탈로그에 **즉시 라이브(=사실상 PUBLISHED)** 상태로 꽂는다. `MarketplaceSkill`(lifecycle_state)은 생성되지 않아 DRAFT/REVIEW/APPROVED를 전부 건너뛴다. 미검토 스킬이 Composer 노드 후보 검색을 오염시킬 수 있다.

## Decision

### 1. Option B — NodeDefinition은 PUBLISHED 시점에만 카탈로그 upsert

미검토 스킬이 카탈로그/검색을 오염시키지 않도록, `NodeDefinition`은 `lifecycle_state == PUBLISHED`가 될 때만 생성·upsert한다.

> **대안 A 기각**: 즉시 upsert + 검색에서 `lifecycle_state` 필터링. → `NodeDefinition`에 lifecycle을 추가하거나 nodes_graph 검색이 marketplace lifecycle을 알아야 해서 **nodes_graph ↔ marketplace 결합**이 생긴다. (d) NodeDefinition은 공유 카탈로그 개념을 유지해야 하므로 기각.

### 2. scope별 lifecycle 진입 분기

Skills Builder 추출 후 scope(personal/team/company)에 따라 진입:

| scope | Skill Builder 페이지에서 | REVIEW 이후 |
|-------|--------------------------|-------------|
| personal | DRAFT→REVIEW→APPROVED→PUBLISHED 전 과정 in-place (owner=본인) | (그 자리에서 완결) |
| team / company | DRAFT 저장까지만 | Marketplace에서 리뷰어가 진행 |

UX 근거: personal은 본인이 쓸 스킬이라 그 자리 완결이 자연스럽고, team/company는 타인(리뷰어) 검토가 필요하니 Marketplace가 거처. "추출 결과 검토 wizard 부재"도 personal in-place 흐름으로 해소.

### 3. Q1~Q7 확정 (2026-05-21 조장·박아름 합의)

| # | 결정 | 근거 |
|---|------|------|
| **Q1** DRAFT 노드스펙 거처 | `MarketplaceSkill.node_definition_id` → `UUID \| None`. 노드 스펙(`category`/`input_schema`/`output_schema`/`risk_level`/`required_connections`/`service_type`)을 **staging 필드**로 보관 → publish 시 `NodeDefinition` 생성. PR-2e DDL에 staging 컬럼 | (a)(d) — NodeDefinition은 PUBLISHED 전 존재 안 함 |
| **Q2** personal self-review | `SkillLifecycle` 4전이 모두 기록(audit), UI만 personal "검토→게시" 한 번으로 합침. self-approval 허용(owner=reviewer_id). **`ApprovalWorkflow` 실제 연결**(레코드 저장) | (+) 감사 추적 |
| **Q3** team/company 직접 생성 | **불가 — promotion-only 유지**. Skill Builder 직접 생성은 personal만, team/company는 `PromoteToTeam/Company`로 | (c) 직접 생성 경로 없음 + "promotion=복제" 일관 |
| **Q4** lifecycle use case 호출 위치 | `api_server`에 scope-aware lifecycle 라우트(submit/approve/publish) 신설 → skills_marketplace `ApproveSkill`/`PublishSkill` 호출 (Composition Root) | — |
| **Q5** 검색/가시성 | **company PUBLISHED만 nodes_graph 카탈로그**(공유) → Composer가 `NodeDefinitionRepository`로 검색. **personal/team은 `SkillRepository.search`(scope+멤버십+lifecycle 필터)** 별도. Composer 노드후보 = 카탈로그(company) + marketplace search(personal/team) | (d) NodeDefinition에 scope/owner 없어 멤버십 필터 불가 |
| **Q6** batch 단위 | batch(SOP 1건=1 scope) 기본 + 스킬별 override는 후속 | — |
| **Q7** seed 경로 | seed(industry/functional)는 사전 큐레이션이라 **company scope 자동 PUBLISHED**(리뷰 생략). `source_type` 게이트(seed=자동 / sop=lifecycle) | 박아름 큐레이션 검증본 |

### 4. 아키텍처 축 — NodeDefinition vs MarketplaceSkill 분리

- `NodeDefinition` = scope/lifecycle 없는 **공유 카탈로그** (company PUBLISHED만, 전체 노출)
- `MarketplaceSkill` = scope + lifecycle_state 보유 (personal/team은 marketplace에만)

personal/team은 멤버십 필터가 필요한데 NodeDefinition이 scope/owner를 못 담으므로(d), **카탈로그가 아닌 marketplace `SkillRepository`로만** 관리한다. Q1(staging)·Q5(검색 이원화)·Q7이 모두 이 분리에서 파생.

### 5. 선행 코드 부채 2개 (본 설계 전제)

1. **`SkillRepository.search`에 `lifecycle_state` 필터 추가** — 현재 scope/include_promoted만. PUBLISHED만 노출하려면 필수.
2. **`ApprovalWorkflow` 실제 연결** — 현재 엔티티 정의만 있고 `ApproveSkillUseCase`가 reviewer_id를 받지만 레코드를 저장 안 함.

## Consequences

### 외부 모듈 영향

- **ai_agent** (REQ-004, 박아름) — `BuildFromXxx` 3종: `NodeDefinitionRepository.upsert()` 제거 → `MarketplaceSkill` DRAFT emit으로 변경. `ResultFrame.payload` 형태 변경. agent-skills-builder Modal 라우팅/응답 변경.
- **skills_marketplace** (REQ-013, 박아름) — `MarketplaceSkill.node_definition_id` Optional + 노드 스펙 staging 필드. `SkillRepository.search` lifecycle 필터. `ApproveSkillUseCase`에 ApprovalWorkflow 저장. publish 시 NodeDefinition 생성 로직.
- **api_server** (REQ-009, 황대원) — scope-aware skill lifecycle 라우트(submit/approve/publish) 신설.
- **nodes_graph** (REQ-003, 박아름) — Composer 노드 후보 검색에서 company 카탈로그 + personal/team marketplace search 이원화.
- **database** (REQ-001, 황대원) — PR-2e DDL에 staging 컬럼 + lifecycle_state 인덱스.
- **frontend** (REQ-010) — Skill Builder 페이지 scope 선택 UI + (personal) in-place 검토 UI.

### 긍정

- 미검토 스킬이 카탈로그/검색을 오염시키지 않음 (HITL 게이트 실효화).
- `NodeDefinition` 공유 카탈로그 개념 유지 (nodes_graph ↔ marketplace 결합 회피).
- personal in-place로 self-review wizard 부재 해소.
- promotion-only 유지로 모델 단순.

### 부정 / 제약

- `BuildFromXxx` 3종 + MarketplaceSkill 스키마 + api_server 라우트 + 검색 이원화 + frontend = 광범위 변경. 단계화 필요.
- 노드 스펙 staging ↔ NodeDefinition 이중 표현 (publish 시 변환).
- 검색 이원화(카탈로그 + marketplace search)로 Composer 검색 로직 복잡.

## Alternatives Considered

### A. 즉시 upsert + 검색에서 lifecycle 필터 (기각)
- NodeDefinition에 lifecycle/scope 추가 또는 nodes_graph 검색이 marketplace lifecycle 인지 → nodes_graph ↔ marketplace 결합. (d) 공유 카탈로그 개념 위반.

### B. NodeDefinition은 PUBLISHED만 카탈로그 + scope별 진입 (본 ADR 채택)
- ✅ 모듈 경계 깔끔, HITL 게이트 실효, 공유 카탈로그 유지.

## Related ADRs

- **ADR-0012** — database/storage/skills_marketplace 책임 분배 (MarketplaceSkill 3계층).
- **ADR-0017** — Skills Builder 산출물 NodeDefinition + SkillDocument 이중 저장. 본 ADR이 그 산출물의 게시 lifecycle을 정의.
- ADR-0018 — 노드 독립 실행 경로 (NodeDefinition 카탈로그 실행).

## References

- 설계 논의: 2026-05-21 조장 → 박아름 (Skills Builder 산출물 5단계 lifecycle 우회)
- 코드 검증: `marketplace_*_skill.py` (node_definition_id Required), `skill_lifecycle.py` (5전이), `skill_repository.py` (search lifecycle 필터 부재), `node_definition.py` (scope/lifecycle 필드 부재), `promotion_service.py` (promotion-only), `approve_skill_use_case.py` / `approval_workflow.py` (ApprovalWorkflow 미사용), `build_from_sop_use_case.py` (즉시 upsert)
