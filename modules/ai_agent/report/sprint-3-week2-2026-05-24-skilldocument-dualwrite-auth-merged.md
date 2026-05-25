# Sprint 3 Week 2 — 박아름 작업 현황 (2026-05-24, 사이클 마감)

> ADR-0020 위임2 + ADR-0017 SkillDocument 이중 저장 호출부 배선 + `/auth/me` 프로필 노출
> 관련 ADR: `ADR-0020`(게시 lifecycle), `ADR-0017`(SkillDocument 이중 저장)

## 요약

2026-05-24 박아름 사이클 — 8개 PR 머지 완료(`#158/#159/#160/#161/#163/#164/#165/#171`, development `c495396`. + 문서 동기화 #167). ADR-0020 위임2(게시 인가)와 ADR-0017 SkillDocument 이중 저장이 **`doc_store` 주입(#171)까지 머지**돼 SOP wizard `confirm` → personal DRAFT 생성 시 SKILL.md를 GCS에 저장하는 경로가 **코드 전부 완성**. 실제 GCS 저장 활성화는 조장 인프라(전용 버킷 GCP Secret + Modal SA Storage 권한) + Modal 재배포만 남음. `/auth/me`는 프론트 userName 연결용 `email`/`name`을 반환한다.

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
| **#171** | 박아름 | agent-skills-builder Modal composition root(`main.py`)에서 `CreateDraftSkillUseCase`에 `doc_store` 주입 + image `google-cloud-storage`/`pyyaml` + boot 버킷 tolerant 로드(NotFound=info / 권한·설정오류=error 구분). 버킷 env 미설정 시 `doc_store=None`(문서 미저장, deploy-safe) |

- 흐름: `extract_draft`(추출) → `confirm`(instructions 전달) → `CreateDraftSkillUseCase`(skill_id 생성 → `doc_store.save` → 반환 URI를 `skill_document_uri`에 세팅) → 메타 저장.

### `/auth/me` 프로필 노출 — PR #163 (가원 요청, 조장 위임)

- `MeResponse(PermissionSource)` — 인가 컨텍스트 필드 + `email` + `name`. `PermissionSource`(모든 보호 라우트 공유)에 PII를 싣지 않고 `/me` 전용 응답에서만 합성.
- `get_current_user` 의존성 신설(User 조회 단일 소스). `get_permission_source`가 이를 경유 → FastAPI 의존성 캐싱으로 `/auth/me` User 조회 1회(가원 리뷰 반영).

### 검증

- skills_marketplace **67** / skills_builder **116** / api_server auth **11** / agent-skills-builder integration **20** passed, 전건 ruff clean.
- 자체 3축 리뷰(클린아키/타모듈 import/스펙 정합) — 위반 0. 조장 박아름 4 PR(#163/#164/#165/#171) 전건 Approve.

### 스펙 정합 (동기화 완료)

- REQ-013 §2.4(SkillDocumentStore 위치 `storage/adapters` 확정·`save→str`)·§2.5(`CreateDraftSkillUseCase` `instructions?`)·§2.1(SkillDocument SSOT=common_schemas)
- REQ-004 §L135(confirm instructions 흐름)·L170(adapter 위치 확정)
- REQ-009 L94(`/auth/me` → `MeResponse`)
- ADR-0017 §위치/Follow-up

## 잔여 (전부 박아름 코드 외 — 인프라/협업 대기)

> 박아름 코드·테스트·문서·셀프리뷰·PR 전부 완료. 카톡 3건(가원/조장/신정혜) 발송 完(2026-05-24).

1. **agent-skills-builder 재배포 完(2026-05-25 12:46, v6) — 단 e2e smoke 차단(`db:unreachable`)**: 조장 인프라 完(#178 secret + 8 accessor binding + bucket objectAdmin). 박아름 `modal deploy`로 v6 배포 → doc_store deps(google-cloud-storage/pyyaml) 정상, **부팅 성공**(ImportError 0). **그러나 `/v1/health`=`db:unreachable`(2회)** → `CreateDraftSkillUseCase.save_personal`(DB) 차단으로 e2e smoke 불가. DB 연결 로직 무변경(메모리상 5/19 `db:iam-connected`였음) → 최근 SA 격리 인프라(#168/#172/#174/#177)가 공유 `cloudsql-iam-modal` SA의 Cloud SQL DB IAM 접근에 영향 줬거나 staging 인스턴스 정지 의심 = **조장 DB/SA infra 확인 대기**(2026-05-25 카톡 발송). DB 복구 시 SOP confirm → GCS `skills/{skill_id}/SKILL.md` 생성 smoke.
2. **프론트 userName 연결** (가원, REQ-010) — `useAuth.ts`의 `userName: ''` → `userName: user.name`(+ `me()` 응답 타입 MeResponse). 연결 시 PR #149 must-fix(AppBar ` · User`) 완전 해소. #163 머지로 unblock.
3. **Composer SkillRetriever** (신정혜, ADR-0017 §3) — `SearchSkillsUseCase` 소비. FYI 핸드오프.
4. **staging deploy / 인프라** (조장) — terraform/api_server + 위 ①② secret·SA 권한.

## 다음 단계

1. (조장) agent-skills-builder SA의 staging DB IAM 접근 복구(`db:unreachable`) → (박아름) e2e smoke (재배포 자체는 v6 完)
2. (가원) 프론트 연결 / (신정혜) Composer SkillRetriever — 별도 트랙
