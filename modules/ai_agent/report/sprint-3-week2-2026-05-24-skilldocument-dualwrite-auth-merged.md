# Sprint 3 Week 2 — 박아름 작업 현황 (2026-05-24, 사이클 마감)

> ADR-0020 위임2 + ADR-0017 SkillDocument 이중 저장 호출부 배선 + `/auth/me` 프로필 노출
> 관련 ADR: `ADR-0020`(게시 lifecycle), `ADR-0017`(SkillDocument 이중 저장)

## 요약

2026-05-24 박아름 사이클 — 7개 PR 머지 완료(development `c84706f`). ADR-0020 위임2(게시 인가)와 ADR-0017 SkillDocument 이중 저장 "지침서" 측 **호출부 배선**이 끝나, SOP wizard 추출 → personal DRAFT 생성 시 SKILL.md를 GCS에 저장하는 경로가 코드 레벨에서 완성됐다(실제 활성화는 `services/agents/agent-skills-builder/main.py` `doc_store` 주입 후속). `/auth/me`는 프론트 userName 연결용 `email`/`name`을 반환한다.

## 완료 (머지)

### ADR-0020 위임2 — 게시 인가 enforcement (PR #158 + #159)

- `SkillApprovalPolicy`(skills_marketplace domain/services) — Approve/Publish actor 인가 role base. Admin=전체 / personal=`actor==owner` / team=`team_manager`+`actor.department_id==skill.team_id` / company=`company_manager`. 실패 시 `AuthorizationError`(fail-closed), `PermissionSource` 비의존(primitive 입력).
- PR #159(조장): api_server approve/publish 라우트가 `PermissionSource`에서 actor 추출 → use case 전달.
- 머지 순서 #158 → #159 준수(시그니처 정합).

### ADR-0017 SkillDocument 이중 저장 배선

| PR | 담당 | 내용 |
|----|------|------|
| **#160** | 조장 | `GcsSkillDocumentStore`(storage/adapters) — `ObjectStoragePort` 조합, `save()→str(gs:// URI)`, `GCSAdapter.download` NotFound 정규화. 박아름 리뷰 반영(버킷 분리 + pyyaml + 스펙) |
| **#161** | 조장 | `SKILLS_MARKETPLACE_BUCKET` 전용 버킷 인프라 (박아름 M1 리뷰 반영) |
| **#164** | 박아름 | Port `SkillDocumentStore.save() → str` + `CreateDraftSkillUseCase`에 `doc_store`(Optional)/`instructions` 추가 — skill_id를 use case가 생성해 문서저장→메타저장 ordering 일관 처리. doc_store/instructions 둘 중 하나라도 없으면 미저장(하위호환) |
| **#165** | 박아름 | `BuildFromSOPUseCase.confirm`이 드롭하던 `instructions`를 `CreateDraftSkillUseCase.execute(instructions=)`로 전달 — confirm 신뢰경계(str/빈값 None 격리) |

- 흐름: `extract_draft`(추출) → `confirm`(instructions 전달) → `CreateDraftSkillUseCase`(skill_id 생성 → `doc_store.save` → 반환 URI를 `skill_document_uri`에 세팅) → 메타 저장.

### `/auth/me` 프로필 노출 — PR #163 (가원 요청, 조장 위임)

- `MeResponse(PermissionSource)` — 인가 컨텍스트 필드 + `email` + `name`. `PermissionSource`(모든 보호 라우트 공유)에 PII를 싣지 않고 `/me` 전용 응답에서만 합성.
- `get_current_user` 의존성 신설(User 조회 단일 소스). `get_permission_source`가 이를 경유 → FastAPI 의존성 캐싱으로 `/auth/me` User 조회 1회(가원 리뷰 반영).

### 검증

- skills_marketplace **67** / skills_builder **116** / api_server auth **11** passed, 전건 ruff clean.
- 자체 3축 리뷰(클린아키/타모듈 import/스펙 정합) — 위반 0. 조장 3 PR 전건 Approve.

### 스펙 정합 (동기화 완료)

- REQ-013 §2.4(SkillDocumentStore 위치 `storage/adapters` 확정·`save→str`)·§2.5(`CreateDraftSkillUseCase` `instructions?`)·§2.1(SkillDocument SSOT=common_schemas)
- REQ-004 §L135(confirm instructions 흐름)·L170(adapter 위치 확정)
- REQ-009 L94(`/auth/me` → `MeResponse`)
- ADR-0017 §위치/Follow-up

## 잔여 (박아름 / 협업)

1. **`doc_store` 주입 wiring** (박아름) — **`services/agents/agent-skills-builder/main.py`**(Modal Skills Builder 서비스, `CreateDraftSkillUseCase` 실제 조립 위치 `main.py:350`) composition root에서 `doc_store=GcsSkillDocumentStore(...)` 주입 → SkillDocument 실제 GCS 저장 활성화. (api_server엔 호출부 0건) + staging redeploy(조장 Notice — #165 `execute(instructions=)` 런타임 정합).
2. **프론트 userName 연결** (가원, REQ-010) — `useAuth.ts`의 `userName: ''` → `userName: user.name`(+ `me()` 응답 타입 MeResponse). 연결 시 PR #149 must-fix(AppBar ` · User`) 완전 해소.
3. **staging smoke 검증** — 조장 terraform/api_server deploy 대기.

## 다음 단계

1. `services/agents/agent-skills-builder/main.py` `doc_store` 주입 wiring (`main.py:350` CreateDraftSkillUseCase 조립부)
2. 가원 프론트 연결 + staging redeploy 후 e2e 확인
