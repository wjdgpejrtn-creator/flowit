# Sprint 3 Week 2 — 2026-05-24 (일) 박아름 위임2 인가(SkillApprovalPolicy) 보고

## 작업 요약

ADR-0020 **위임2** — Skills Marketplace 게시 lifecycle(승인/게시)의 **actor 인가(role base) enforcement** 구현. 조장 role 인프라(PR #157) 위에 skills_marketplace `SkillApprovalPolicy`를 얹어 scope별 승인 권한을 강제한다.

- **PR**: [#158 feat(req-013): SkillApprovalPolicy](https://github.com/billionaireahreum/Workflow_Automation/pull/158)
- **branch**: `feature/req-013-skills-marketplace` → base=`development` ([[feedback_branch_strategy]])
- **선결**: PR #157 (조장, 박아름 리뷰 ① SSOT 통합 반영 후 머지 2026-05-24) — `common_schemas.UserRole` SSOT 4종 + `PermissionResolver` 매니저 정책 + DB `021`

## 구현 내용

### `SkillApprovalPolicy` (domain/services, 신규)

- `authorize(*, scope, actor_user_id, actor_role, actor_department_id, skill_owner_user_id, skill_team_id) → None` — 실패 시 `AuthorizationError`(**fail-closed**)
- 규칙:
  - **Admin** = superuser (모든 scope — 2026-05-24 박아름 결정, `PermissionResolver` Admin=전체 scope 정합)
  - **personal** = `actor_user_id == skill_owner_user_id` (Ownership, `E-PERM-002`)
  - **team** = `role=="team_manager"` AND `actor_department_id == skill_team_id` (RBAC, `E-PERM-001`)
  - **company** = `role=="company_manager"` (RBAC, `E-PERM-001`)
- **primitive 입력** — `PermissionSource` 비의존(도메인 순수성). role 값 SSOT = `common_schemas.UserRole`.

### use case 배선

- `ApproveSkillUseCase.execute`: `+ actor_role / actor_department_id` (keyword-only). reviewer=actor. **fetch(404) → 인가(403) → 전이** 순.
- `PublishSkillUseCase.execute`: `+ actor_user_id / actor_role / actor_department_id` (keyword-only).

### team 인가 모델 (조장 PR #157 정합)

- team 승인 = `actor.department_id == skill.team_id` 매칭. department = 팀 레지스트리(`departments.sql` seed, 개발팀 `…0000d1`).
- team_id ↔ department_id 값 정합은 **FK 부재로 컨벤션** — 생성/승격(promote) 호출부가 `team_id=department_id` 보장.

## 테스트

- `test_skill_approval_policy.py` **12건** (3 scope allow/deny + Admin 우회)
- `test_lifecycle_use_cases.py` use case authz 추가 (personal 거부 / team 매니저 허용·거부) + 기존 테스트 actor 반영
- `test_publish_node_definition.py` actor 인자 반영
- **skills_marketplace 64 passed**, 신규 코드 ruff clean

## 셀프 리뷰 (박아름 3축 룰)

| 축 | 결과 |
|----|------|
| 클린 아키텍처 의존성 위반 | ✅ 0건 — policy = domain/services 순수, primitive 입력(`PermissionSource`/프레임워크 비의존) |
| 타 모듈 import 문제 | ✅ `common_schemas`(`UserRole`/`AuthorizationError`)만. nodes_graph/auth 직접 import 없음 |
| 스펙 업데이트 | ✅ spec REQ-013 §2.3/2.5 + README domain/services·use_cases 갱신 |

## 후속

- **api_server**(REQ-009, 조장): approve/publish 라우트(PR #150)가 인증 actor의 `PermissionSource`에서 `role`/`department_id`/`user_id`를 꺼내 use case로 전달 (카톡 통보 完). 라우트 어댑션 전까지 use case 계약 불일치 — 본 PR 머지 시 조장 동반 필요.
- GCS `SkillDocumentStore`(ADR-0017 이중저장)는 별도 deferred 항목 (port+entity만 존재).
