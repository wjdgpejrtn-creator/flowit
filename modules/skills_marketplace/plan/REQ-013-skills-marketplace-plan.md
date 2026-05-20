# REQ-013 Skills Marketplace 모듈 구현 Plan

**브랜치**: `feature/req-013-skills-marketplace`
**담당자**: 박아름 (2026-05-20 조장 → 박아름 이관 확정)
**작성일**: 2026-05-20
**참조 스펙**: `docs/specs/REQ-013-skills-marketplace.md`
**참조 ADR**: ADR-0012 v3 (모듈 분리), ADR-0017 (NodeDefinition + SkillDocument 이중 저장)

---

## 구현해야 하는 클래스 목록

### Domain Layer

| 클래스 | 파일 경로 | 상태 |
|--------|-----------|------|
| `MarketplacePersonalSkill` | `domain/entities/marketplace_personal_skill.py` | ✅ 완료 (PR-2d) |
| `MarketplaceTeamSkill` | `domain/entities/marketplace_team_skill.py` | ✅ 완료 |
| `MarketplaceCompanySkill` | `domain/entities/marketplace_company_skill.py` | ✅ 완료 |
| `ApprovalWorkflow` | `domain/entities/approval_workflow.py` | ✅ 완료 (storage 이전) |
| `SkillDocument` | `common_schemas/skill_document.py` (shim: `domain/entities/`) | ✅ common_schemas SSOT 재노출 shim (PR #111 승격, ADR-0017 재정정 — 생산 ai_agent + 저장 skills_marketplace 공유 타입) |
| `SkillScope` (Enum) | `domain/value_objects/skill_scope.py` | ✅ 완료 |
| `SkillState` (Enum) | `domain/value_objects/skill_state.py` | ✅ 완료 (셀프 리뷰 GAP 정정 — services에서 분리) |
| `PromotionService` | `domain/services/promotion_service.py` | ✅ 완료 (범위 승격) |
| `SkillLifecycle` | `domain/services/skill_lifecycle.py` | ✅ 완료 (게시 전이, storage 이전) |
| `SkillRepository` (ABC) | `domain/ports/skill_repository.py` | ✅ 완료 — 구현은 storage |
| `SkillDocumentStore` (ABC) | `domain/ports/skill_document_store.py` | ✅ 완료 — GCS adapter 후속 (위치 PR-2d/2e 결정) |

### Application Layer

| 클래스 | 파일 경로 | 상태 |
|--------|-----------|------|
| `PromoteToTeamUseCase` | `application/use_cases/promote_to_team_use_case.py` | ✅ 완료 (PR-2d) |
| `PromoteToCompanyUseCase` | `application/use_cases/promote_to_company_use_case.py` | ✅ 완료 |
| `SearchSkillsUseCase` | `application/use_cases/search_skills_use_case.py` | ✅ 완료 (repo.search 위임) |
| `ApproveSkillUseCase` | `application/use_cases/approve_skill_use_case.py` | ✅ 완료 (storage 이전 + 정석 정정) |
| `PublishSkillUseCase` | `application/use_cases/publish_skill_use_case.py` | ✅ 완료 (storage 이전) |

---

## 두 lifecycle 축 (옵션 A, 2026-05-20 조장 합의)

- `scope` (범위): `SkillScope` PERSONAL → TEAM → COMPANY — `PromotionService`
- `lifecycle_state` (게시): `SkillState` draft → review → approved → published → archived — `SkillLifecycle`
- 한 스킬이 두 축 동시 보유

### 승격 의미론 = 복제(원본 유지) (조장 리뷰 #98 반영, 2026-05-20)

- scope 승격 = **복제**(원본 유지, 이동 X) — `promoted_from`(역) + `promoted_to_team_id`/`promoted_to_company_id`(순) 양방향 추적
- `search(include_promoted=False)` 기본 → 승격 완료 원본 제외 (중복 노출 방지, WHERE 필터는 storage 구현)
- 게시상태는 승격 시 **DRAFT 재심사 리셋** (넓은 scope = 재승인 경유)
- 상세 → `docs/specs/REQ-013-skills-marketplace.md` §승격 의미론

---

## 구현 단계

| 단계 | 작업 | 상태 |
|------|------|------|
| 뼈대 (깊이 1) | 구조 + Port ABC + entity + README | ✅ PR #98 |
| PR-2d | use case 구현 + storage 게시 도메인 복사 + 정석 정정 | ✅ PR #98 흡수 |
| 셀프 리뷰 GAP 정정 | SkillState value_objects 분리 + REQ-013 spec 신설 | ✅ commit `5297d06` |
| **storage 정리 (조장)** | `storage/marketplace/` 원본 삭제 + `pg_skill_repository` → SkillRepository ABC 구현 | ⏳ 카톡 요청 |
| **PR-2e** | 3계층 schema 마이그레이션 (DB DDL) | ⏳ 카톡 협의 |
| **Skills Builder 코드 변경 (ADR-0017)** | SkillDocument 모델 + GCS adapter + BuildFromXxxUseCase 산출물 변경 | ⏳ |

---

## 의존성 (CLAUDE.md)

- skills_marketplace → storage `SkillRepository` (ABC, 구현 storage)
- skills_marketplace → nodes_graph `NodeDefinitionRepository` (스킬↔노드 연결, PR-2d 후속)
- ai_agent → skills_marketplace `SearchSkillsUseCase` (Composer)

---

## 테스트

```bash
PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest modules/skills_marketplace/tests -q
# 16 passed: PromotionService 8 + promote/search 4 + 게시 lifecycle 4
```
