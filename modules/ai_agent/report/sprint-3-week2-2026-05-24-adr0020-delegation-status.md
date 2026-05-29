# Sprint 3 Week 2 — 박아름 작업 현황 (2026-05-24)

> ADR-0020 게시 lifecycle 1차 구현: ③ Skills Builder wizard + 조장 위임 2건
> 관련 ADR: `docs/context/adr/ADR-0020-skills-builder-publish-lifecycle-gate.md`

## 요약

ADR-0020 1차 구현이 ③(Skills Builder wizard)·위임1(Submit)까지 **머지 완료**, 위임2(Approve/Publish 인가)는 **role base 확정 후 조장 role 인프라 대기**. 박아름 5개 브랜치 모두 development(`792de63`) 동기화.

## 완료 (머지)

### ③ Skills Builder wizard — PR #151 (req-004)

- `BuildFromSOPUseCase` wizard 2단계 (ADR-0020 Q8):
  - `extract_draft`: SOP → LLM 추출 → `NodeSpecStaging`+메타 반환, **저장 X**(사용자 검토용)
  - `confirm`: 편집 결과 → `CreateDraftSkillUseCase`로 personal DRAFT (NodeDefinition은 publish 시점, Option B)
- main.py sop 라우팅: `payload["step"]`(extract/confirm) 분기 + `CreateDraftSkillUseCase(PgMarketplaceSkillRepository)` 조립 — 조장 SkillRepository(PR #147) 머지로 블로커 해소
- 정합성 정비: spec REQ-004 §2.2 + README ai_agent + docstring + `__init__` functional export + CLAUDE.md value_objects 교차 import 명시(`0ee94be`)
- **조장 리뷰 M1/M2 반영**(`108abde`):
  - M1: `confirm`이 wizard 신뢰 경계임을 반영 — staging/name/description 파싱 + category 재검증을 try 격리 → malformed면 `E_SKILL_INVALID` ErrorFrame(예외 미전파). main.py `payload.get("skills", [])`
  - M2: 실패경로 테스트 6건 — extract `E_LLM_GENERATION_FAILED`/`E_LLM_RESPONSE_INVALID` + confirm malformed/bad_category/embed/create_draft 격리
- 검증: skills_builder **115 passed**, ruff clean

### 위임1 SubmitSkillUseCase — PR #154 (req-013)

- `DRAFT → REVIEW` 게시 검토 제출 use case (PR #150 조장 위임 1/2)
- approve/publish 동일 패턴(`SkillLifecycle` 위임 + scope별 get/save)
- spec REQ-013 §2.5 + README 반영, skills_marketplace **49 passed**
- 조장 리뷰 Approve(무지적). submit 라우트(`POST /skills/{id}/submit`)는 조장 REQ-009 후속 조립

## 대기

### 위임2 Approve/Publish 인가 enforcement — role base (PR #150 위임 2/2)

- **확정(2026-05-22 조장)**: `team_manager`/`company_manager` 권한 role 부여 방식
- **계기**: personal=소유자(`owner_user_id==actor`) 판정은 가능하나, team/company 멤버십 판정 데이터 부재(User에 team 필드 없음 + user-team 관계 테이블 없음) → 멤버십 테이블 대신 role base 채택
- **블로커**: 조장 role 인프라(auth role 확장, 기존 User/Admin 외) — 2026-05-24 development/OPEN PR에 아직 없음
- **⚠️ 분담 확인 필요**: role enum은 auth(REQ-002 박아름) 영역과 연관 — 조장이 role 인프라 진행 시 분담 합의
- role 인프라 머지 후 박아름이 use case role 검증(personal=소유자 / team=`team_manager` / company=`company_manager`) 구현

## 조장 분담 (완료)

- PR #147 `PgMarketplaceSkillRepository`(SkillRepository 3-scope) + DDL(3계층 staging + skill_approvals.scope)
- PR #148 storage `marketplace/` 구복사본 삭제
- PR #150 게시 lifecycle 라우트(approve/publish, Q4)

## 다음 단계

1. 위임2 인가 enforcement — 조장 role 인프라 머지 대기
2. (병렬) staging smoke 검증 — 조장 terraform/api_server deploy 대기
