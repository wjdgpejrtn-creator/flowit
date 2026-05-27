# Sprint 3 Week 2 — 박아름 작업 현황 (2026-05-24 사이클 + 5/26 e2e 종결)

> ADR-0020 위임2 + ADR-0017 SkillDocument 이중 저장(호출부 배선 → 5/26 e2e 검증 종결) + `/auth/me` 프로필 노출
> 관련 ADR: `ADR-0020`(게시 lifecycle), `ADR-0017`(SkillDocument 이중 저장)

## 요약

2026-05-24 박아름 사이클 — 8개 PR 머지 완료(`#158/#159/#160/#161/#163/#164/#165/#171`, development `c495396`. + 문서 동기화 #167). ADR-0020 위임2(게시 인가)와 ADR-0017 SkillDocument 이중 저장이 **`doc_store` 주입(#171)까지 머지**돼 SOP wizard `confirm` → personal DRAFT 생성 시 SKILL.md를 GCS에 저장하는 경로가 **코드 전부 완성**. `/auth/me`는 프론트 userName 연결용 `email`/`name`을 반환한다.

> **2026-05-26 갱신·종결**: 조장 #178(버킷)+#179/#180(db:unreachable 해소) 후 e2e smoke 실행 → `personal_skills` 등 020 4테이블의 런타임 SA GRANT 누락 발견 → **조장 즉시 fix(3 SA 일괄 GRANT + ALTER DEFAULT PRIVILEGES)** → **재실행 full e2e PASS(`created_count:1`)로 ADR-0017 SkillDocument 이중저장(DB 메타 + GCS SKILL.md)이 staging에서 완전 검증·종결**. 박아름 영역 잔여 0(테스트 데이터 정리만). 도중 Modal 앱 2개 404 드롭→재배포 복구(별건). 상세는 아래 §잔여 1번.

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
- REQ-004 §2.2 skills_builder(`BuildFromSOPUseCase.confirm` instructions 흐름 + `SkillDocumentStore` adapter 위치 = `storage/adapters`)
- REQ-009 §2.2 Routes(`/auth/me` → `MeResponse`)
- ADR-0017 §위치/Follow-up

## 잔여 (전부 박아름 코드 외 — 인프라/협업 대기)

> 박아름 코드·테스트·문서·셀프리뷰·PR 전부 완료. 카톡 3건(가원/조장/신정혜) 발송 完(2026-05-24).

1. **✅ e2e smoke full PASS·종결(2026-05-26) — ADR-0017 이중저장 staging 완전 검증**:
   - **db:unreachable 해소**: 5/25 `db:unreachable`은 SA 격리 작업(#168/#172/#174/#177)이 공유 `db-iam-user` secret을 일시 흔든 것. 조장 #179(db-iam-user-api prep)/#180(api_server db-iam-user-api 전환, 옵션 C 3-secret 격리 완성) 후속으로 `db-iam-user` v4=`cloudsql-iam-modal` email 복원 → Modal sub-agent 3종 unblock. `GET /v1/health` = `db:iam-connected`(HTTP 200) 직접 확인.
   - **smoke 결과**: `POST /v1/agent/route`(source_type=sop, step=confirm, owner=seed system_user). ✅ confirm 라우팅 / ✅ `embed`(llm-base BGE-M3) / ✅ `CreateDraftSkillUseCase` 진입 / ✅ **`doc_store.save()` → GCS `skills/{skill_id}/SKILL.md`** — `gcloud storage cat`으로 frontmatter(name/description)+markdown body 직렬화 확인. **ADR-0017 GCS 이중저장 절반 = 배포본 정상 배선 + 쓰기 동작 staging 검증 完**(신규 코드 검증).
   - ❌ **`save_personal()`(session.merge=SELECT先)** → `asyncpg.InsufficientPrivilegeError: permission denied for table personal_skills`. DB 연결은 OK(health), **테이블 GRANT 누락**. terraform `google_sql_user.iam_users`는 Cloud SQL 인증 유저만 생성(`SELECT 1` 통과), PG 테이블 GRANT는 수동 관리(`docs/guides/cloud-sql-setup.md` §4/§4-1)인데 `personal_skills`(ADR-0020 `020_skills_marketplace_staging.sql`)가 런타임 SA `cloudsql-iam-modal`에 미부여. team/company_skills·skill_approvals 동반 누락 추정.
   - **조장 GRANT 즉시 fix(2026-05-26)**: 020 4테이블 모두 `cloudsql-iam-modal` GRANT 누락 + **`company_skills`는 전(全) SA 누락**까지 발견. 3 SA(`cloudsql-iam-modal`+`workflow-api-staging-sa`+`workflow-worker-staging-sa`)에 `GRANT ALL TABLES` + `USAGE,SELECT SEQUENCES` 일괄 + `workflow_admin` owner `ALTER DEFAULT PRIVILEGES`(신규 테이블 자동 GRANT). 검증 4테이블×3SA=12row×7priv.
   - **영구 fix = PR #183 머지**(조장, dev `713f640`): `MigrationRunner`가 `SET LOCAL ROLE workflow_admin` 후 CREATE → 테이블 owner 일관화 → `ALTER DEFAULT PRIVILEGES` 정확 트리거 → **향후 신규 schema 자동 GRANT**. 이번 누락은 memory `staging_db_state` **함정 #11(신규 schema SA GRANT 누락)/#12(SA 분리 일괄 GRANT race → company_skills)의 발현**. ⚠️ #183은 **신규** schema만 자동 차단 — **기존** owner drift는 본 사례가 마지막이 아닐 수 있음(조장 follow-up: 기존 drift 별도 ALTER OWNER 정리).
   - **✅ 재실행 full e2e PASS**: `created_count:1 / failed_count:0 / skill_ids=[db3e3a45-3690-42e0-a6f4-cd90d6f37665]`, HTTP 200. embed→create_draft(GCS save 先→DB `save_personal`)까지 전부 성공 = **ADR-0017 이중저장 e2e 완전 검증 종결**. (GCS save가 DB보다 먼저라 PASS 자체가 GCS+DB 양쪽 성공을 함의.) **이중저장 링크 입증**: 정리 시 SELECT한 `personal_skills` row의 `skill_document_uri` = `gs://…/skills/db3e3a45-…/SKILL.md`로 정확히 세팅됨(DB 메타 ↔ GCS 문서 연결 확인).
   - **⚠️ Modal 앱 드롭 사건(별건, 추적 필요)**: smoke 재실행 중 agent-skills-builder + llm-base 두 앱이 `modal-http: invalid function call` 404(앱 전체)로 드롭 → 박아름 `modal deploy` 재배포로 각각 복구(agent 29.9s / llm-base 4.8s, health 200 회복). 한 세션 2개 연속 드롭 = 워크스페이스에서 앱이 자꾸 stop되는 정황 → **조장/신정혜에 Modal 안정성 공유 권장**(원인 미확정).
   - **설계 노트(GCS-first ordering)** ⟶ **추적 항목 승격(아래 다음 단계 ②)**: `CreateDraftSkillUseCase`는 GCS save가 DB save보다 먼저 → DB 실패 시 GCS orphan(`skills/728940fc-…/SKILL.md`, GRANT 누락 1차 실패분) 잔존(rollback 안 됨, skill_id=uuid4라 재시도마다 누적). **GRANT 외 사유(제약 위반·일시 장애 등)로 DB fail 시에도 동일 orphan 누적** → ADR-0017 후속으로 보상 삭제 or 저장 순서 검토 필요.
   - **✅ 테스트 데이터 정리 完(2026-05-26)**: orphan `728940fc` + 성공 DRAFT `db3e3a45`(GCS SKILL.md 2건 `gcloud storage rm` + `personal_skills` row 1건 DELETE). 버킷 `skills/` 0건 / DB row 0건 확인. staging에 smoke 잔여물 없음.
2. **프론트 userName 연결** (가원, REQ-010) — `useAuth.ts`의 `userName: ''` → `userName: user.name`(+ `me()` 응답 타입 MeResponse). 연결 시 PR #149 must-fix(AppBar ` · User`) 완전 해소. #163 머지로 unblock.
3. **Composer SkillRetriever** (신정혜, ADR-0017 §3) — `SearchSkillsUseCase` 소비. FYI 핸드오프.
4. **staging deploy / 인프라** (조장) — terraform/api_server + 버킷·SA secret(#161/#178/#179/#180) + **DB GRANT(위 1번)**. 본 사이클 관련 인프라는 전부 적용 完.

## 다음 단계

1. ✅ **ADR-0017 SkillDocument 이중저장 e2e 종결**(2026-05-26) — 박아름 영역 코드/인프라/테스트데이터 정리까지 전부 完. 잔여 0.
2. **(추적) GCS-first orphan 리스크** — DB fail 시 GCS orphan 잔존(rollback 부재). ADR-0017 후속으로 **보상 삭제 or 저장 순서(DB先) 검토**. 조장 리뷰 권고로 별도 추적 항목 승격.
3. **(추적) Modal 앱 드롭 정황** — 한 세션 2개(agent-skills-builder/llm-base) `invalid function call` 404 드롭. 원인 미확정 → **조장/신정혜 운영 이슈 + memory 승격**(재발 시 빠른 인식). memory `staging-db-state`/별도 항목 참조.
4. (가원) 프론트 connection / (신정혜) Composer SkillRetriever — 별도 트랙.
