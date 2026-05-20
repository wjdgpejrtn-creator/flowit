# Sprint 3 Week 2 — 2026-05-20 (수) 박아름 Skills Marketplace 신설 보고

## 작업 요약

`modules/skills_marketplace` (REQ-013) 신규 모듈 신설. 조장 → 박아름 이관 확정. ADR-0012 v3 PR-2d + ADR-0017 기반. 뼈대(깊이 1) + PR-2d 통합 구현 + 셀프 리뷰 GAP 정정까지 단일 PR(#98)에 흡수.

- **PR**: [#98 feat(skills_marketplace): REQ-013 신설](https://github.com/billionaireahreum/Workflow_Automation/pull/98)
- **branch**: `feature/req-013-skills-marketplace` → base=`development` ([[feedback_branch_strategy]] 룰 정합)

## 조장 협의 확정 (5/20)

| 항목 | 결정 |
|------|------|
| REQ 번호 | REQ-013 |
| 영역 이관 | 조장 → 박아름 (CLAUDE.md 담당 표 갱신) |
| entity 구조 | 3개 별도 entity, `Marketplace` 접두사 (ai_agent.PersonalSkill 충돌 회피) |
| SkillRepository 위치 | `skills_marketplace/domain/ports` (Port) + `storage/repositories` (구현) — ADR-0017 |
| 두 lifecycle | scope(범위 승격) + lifecycle_state(게시) 공존 (옵션 A) |

## 구현 내용

### 뼈대 (깊이 1)
- domain 3계층 구조 + Port ABC + entity + value_objects + service + README + pyproject

### PR-2d (통합 구현)
- entity 확장: 3 entity에 lifecycle_state/author_id/workflow_id/tags/version/metadata (storage Skill 흡수)
- 게시 도메인 복사 (storage → skills_marketplace): SkillLifecycle/SkillState + ApprovalWorkflow
- use case 구현: PromoteToTeam/Company + SearchSkills + ApproveSkill/PublishSkill
- 정석 정정: storage approve/publish의 PgSkillRepository 직접 의존(anti-pattern) → SkillRepository ABC

### 셀프 리뷰 GAP 정정 (commit `5297d06`)
- ① 클린 아키텍처: SkillState를 services → value_objects 분리 (entity → service 역방향 의존 해소)
- ② 스펙: docs/specs/REQ-013-skills-marketplace.md 신설

## 셀프 리뷰 (박아름 4축 룰)

| 축 | 결과 |
|----|------|
| 클린 아키텍처 의존성 위반 | ⚠️ GAP(SkillState 위치) → ✅ 정정 (value_objects 분리) |
| 타 모듈 import 문제 | ✅ 0건 (common_schemas만, cross-module 순환/충돌 0) |
| 스펙 정합 | ⚠️ GAP(REQ-013 spec 부재) → ✅ 정정 (spec 신설) |
| SSOT | ✅ (MarketplaceSkill 분리, SkillState SSOT=value_objects) |

## 검증

- pytest modules/skills_marketplace/tests — **16 passed** (PromotionService 8 + promote/search 4 + 게시 lifecycle 4)
- cross-module import (ai_agent/nodes_graph 연결) OK — 순환/충돌 0
- 다른 브랜치 sync 후 회귀 0 (auth/nodes_graph/skills_builder/ai_agent domain 합계 316 passed)

## CLAUDE.md 정정

- L146 SkillRepository 위치: storage 소유 → skills_marketplace 소유 (ADR-0017)
- Port → Adapter 매핑 + storage 교차 import 행 추가
- 담당 표: skills_marketplace 박아름 이관 확정 (REQ-013)

## 조장 후속 (storage 영역 — 박아름 복사만)

1. `storage/marketplace/` 원본 삭제 (중복 제거)
2. `storage/repositories/pg_skill_repository.py` → `skills_marketplace.SkillRepository` ABC 구현 정정

## 다음 작업

| 항목 | 비고 |
|------|------|
| PR #98 머지 | 조장 |
| PR-2e (3계층 DB DDL) | 박아름 + 카톡 협의 ([[feedback_db_safety]]) |
| Skills Builder 코드 변경 (ADR-0017) | 박아름 — SkillDocument 모델 + GCS adapter + 산출물 변경 |
