# skills_marketplace

> REQ-013: Skills Marketplace 도메인 — 3계층(personal/team/company) 스킬 + 승격 lifecycle + 하이브리드 검색
>
> 설계 결정 → [`ADR-0012`](../../docs/context/adr/ADR-0012-database-storage-module-boundary.md) (모듈 분리), [`ADR-0017`](../../docs/context/adr/ADR-0017-skills-builder-skill-document-dual-storage.md) (NodeDefinition + SkillDocument 이중 저장)
>
> **현재 상태: PR-2d (use case 구현 + 게시 도메인 복사)** — promote/search/approve/publish use case 구현 + storage 게시 도메인(SkillLifecycle/ApprovalWorkflow) 복사. storage 원본 삭제 + `SkillRepository` storage 구현은 조장 후속. DB DDL은 PR-2e.

## 역할

사내 Skills Marketplace (외부 [SkillsMP](https://skillsmp.com/) 레퍼런스, **외부 공유 X**). Skills Builder가 생성한 스킬을 personal → team → company 3계층으로 관리하고, Workflow Composer가 사용자 의도와 유사한 스킬을 검색해 옵션 제시한다.

```
Skills Builder (ai_agent) → skills_marketplace 저장 (NodeDefinition 메타 + SkillDocument GCS)
                                    ↓
Workflow Composer (ai_agent) → SearchSkillsUseCase → 사용자에게 옵션 제시
                                    ↓
사용자 승격 요청 → PromoteToTeam/Company → 3계층 lifecycle
```

## 설치

```bash
pip install -e modules/skills_marketplace
pip install -e "modules/skills_marketplace[dev]"
```

## Quick Start

```python
from skills_marketplace.domain.entities import (
    MarketplacePersonalSkill,
    MarketplaceTeamSkill,
    MarketplaceCompanySkill,
)
from skills_marketplace.domain.value_objects import SkillScope
from skills_marketplace.domain.services import PromotionService
from skills_marketplace.domain.ports import SkillRepository
from skills_marketplace.application.use_cases import (
    PromoteToTeamUseCase,
    PromoteToCompanyUseCase,
    SearchSkillsUseCase,
)
```

## Public API

### domain/entities (3계층)

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `MarketplacePersonalSkill` | `skill_id`, `owner_user_id`, `name`, `description`, `node_definition_id`(Optional, ADR-0020 Q1), `node_spec_staging`(Optional `NodeSpecStaging`), `lifecycle_state`, `skill_document_uri`, `embedding`, `promoted_to_team_id`, `created_at`, `updated_at` | 개인 범위 스킬. `ai_agent.PersonalSkill`(메모리)과 도메인 다름 — `Marketplace` 접두사로 충돌 회피. `node_definition_id`는 PUBLISHED 시점에만 채움(그 전엔 `node_spec_staging` 보관, Option B) |
| `MarketplaceTeamSkill` | + `team_id`, `promoted_from` (← 원본 personal), `promoted_to_company_id` (→ 전사 승격 마킹) | 팀 범위. PromoteToTeam으로 승격 |
| `MarketplaceCompanySkill` | + `promoted_from` (← 원본 team) | 전사 범위(최종). PromoteToCompany로 승격 |

> **NOTE**: 필드는 깊이 1(뼈대) 기준. 실제 컬럼/제약은 PR-2e schema 마이그레이션 시 확정.
>
> **승격 의미론 = 복제(원본 유지)** (조장 리뷰 #98): scope 승격은 원본을 유지(이동 X)하고 신규 생성한다. ① 양방향 추적 `promoted_from`(역) + `promoted_to_*`(순), ② `search(include_promoted=False)` 기본으로 승격 완료 원본 제외(중복 노출 방지), ③ 게시상태는 **DRAFT 재심사 리셋**(넓은 scope = 재승인 경유). 상세 → REQ-013 spec §승격 의미론.

### domain/value_objects

| 클래스 | 설명 |
|--------|------|
| `SkillScope` | `str` Enum — `PERSONAL` / `TEAM` / `COMPANY`. 승격 단방향: PERSONAL → TEAM → COMPANY |
| `SkillState` | `str` Enum — `draft`/`review`/`approved`/`published`/`archived`. 게시 상태 (전이 규칙은 `SkillLifecycle` service) |
| `NodeSpecStaging` | publish 전 노드 스펙(`category`/`input_schema`/`output_schema`/`risk_level`/`required_connections`/`service_type`) 임시 보관 (ADR-0020 Q1). PUBLISHED 시 이 staging + 스킬 메타 → `NodeDefinition` 생성 |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `PromotionService` | `can_promote(current, target) → bool`, `next_scope(current) → SkillScope \| None` | 범위 승격 전이 규칙 (순수 로직). 단방향 1단계만 허용 |
| `SkillLifecycle` | `can_transition(current, target) → bool`, `transition(current, target) → SkillState` | 게시 상태 전이 (draft→review→approved→published→archived). storage에서 이전 (옵션 A 공존) |

### domain/entities (게시)

| 클래스 | 설명 |
|--------|------|
| `ApprovalWorkflow` | 게시 승인 워크플로우 항목 (`approval_id`/`skill_id`/`scope`/`reviewer_id`/`status`/`comment`/`reviewed_at`/`created_at`). `ApproveSkillUseCase`가 `SkillRepository.save_approval`로 저장 (ADR-0020 + 감사). `scope`(SkillScope) = skill_approvals polymorphic 구분 (조장 A안) |

### domain/entities (지침서)

| 클래스 | 설명 |
|--------|------|
| `SkillDocument` | 스킬 지침서 (SKILL.md 레퍼런스): `skill_id`, `name`, `description`(frontmatter) + `instructions`(markdown body) + `scripts`/`templates`(선택). ADR-0017 이중 저장 중 GCS 측. **SSOT = `common_schemas` (PR #111) — `domain/entities/skill_document.py`는 재노출 shim** |

### domain/ports (인터페이스 — 구현체는 `modules/storage` / 후속)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `SkillRepository` | `async save_personal/save_team/save_company`, `async get_personal/get_team/get_company`, `async search(query_embedding, scope, limit, include_promoted=False, lifecycle_state=None)`, `async save_approval(approval)` | `storage/repositories/` (PR-2d 후속) |
| `SkillDocumentStore` | `async save(skill_id, document)`, `async load(skill_id)` | GCS adapter (위치 PR-2d/2e 결정). SkillDocument(markdown) GCS 저장 |

> **Port 소유권** (ADR-0017 + 5/20 박아름·조장 합의): Port 정의는 skills_marketplace(소비 모듈)가 소유, 구현체는 storage가 제공 (auth/nodes_graph 일반 패턴). CLAUDE.md L146 정정 반영.

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `CreateDraftSkillUseCase` | `owner_user_id, name, description, node_spec_staging, embedding?, skill_document_uri? → UUID` | Skills Builder(③)가 추출 결과를 personal DRAFT로 생성 (ADR-0020 ②e). NodeDefinition 미생성(① 무관) — 노드 스펙은 `node_spec_staging` 보관. wizard 확정 단계 / one-shot 공통 백엔드 |
| `PromoteToTeamUseCase` | `personal_skill_id, team_id → UUID` | 개인 → 팀 승격 (복제: 메타 승계 + DRAFT 재심사 + promoted_from 역추적 + 원본 promoted_to_team_id 마킹) |
| `PromoteToCompanyUseCase` | `team_skill_id → UUID` | 팀 → 전사 승격 (복제: 동일 정책, 원본 promoted_to_company_id 마킹) |
| `SearchSkillsUseCase` | `query_embedding, scope, limit, lifecycle_state=PUBLISHED → list[Skill]` | 하이브리드 검색 — ai_agent Composer 호출 (repo.search 위임). 기본 PUBLISHED만(ADR-0020 (b), 미검토 오염 방지) |
| `ApproveSkillUseCase` | `skill_id, scope, reviewer_id, approved, comment` | 게시 승인 REVIEW → APPROVED/DRAFT + `ApprovalWorkflow` 레코드 저장(ADR-0020 + 감사 추적) |
| `PublishSkillUseCase` | `skill_id, scope` (생성자 +`node_def_repo`) | 게시 APPROVED → PUBLISHED + **publish 시 `node_spec_staging` → `NodeDefinition` 생성·upsert + `node_definition_id` 연결**(ADR-0020 Option B/Q1, ②d). scope별 owner/team 격리(personal=owner_user_id, team=team_id, company=전역). nodes_graph `NodeDefinitionRepository` 의존 |

## 의존 관계

```
Upstream (이 모듈이 의존):
  ├── common_schemas (REQ-012)      — UtcDatetime 등 공유 타입
  ├── storage (REQ-008)             — SkillRepository ABC 구현체 (PR-2d 후속)
  └── nodes_graph (REQ-003)         — NodeDefinitionRepository (스킬 ↔ 노드 카탈로그 연결, PR-2d 후속)

Downstream (이 모듈에 의존):
  └── ai_agent (REQ-004)            — Workflow Composer가 SearchSkillsUseCase 호출 (노드 후보 검토 시)
```

## 산출물 이중 저장 (ADR-0017)

| 산출물 | 형식 | 저장 위치 |
|--------|------|----------|
| NodeDefinition (메타) | pydantic + JSON Schema | skills_marketplace 테이블 (PostgreSQL, PR-2e) |
| SkillDocument (지침서) | markdown frontmatter + body | GCS 버킷 (`skill_document_uri`) |

## 후속 작업 (PR-2d / PR-2e)

| 단계 | 작업 |
|------|------|
| **PR-2d** | use case 실제 구현 + storage skill 코드 이전 (`storage/marketplace/`, `skill_model.py`, `skill_mapper.py`, `pg_skill_repository.py`) + `SkillRepository` storage 구현 |
| **PR-2e** | 3계층 schema 마이그레이션 (`personal_skills`/`team_skills`/`company_skills` 테이블 DDL) + ORM/Repository — DB 쓰기 수반(카톡 협의 필요) |

## 테스트

```bash
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest modules/skills_marketplace/tests -q
# PromotionService 승격 규칙 8건 (깊이 1)
```
