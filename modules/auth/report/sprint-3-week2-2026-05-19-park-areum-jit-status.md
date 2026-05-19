# Sprint 3 Week 2 — 박아름 REQ-002 보강 JIT user auto-provisioning Status (2026-05-19)

## 작업 요약

조장 2026-05-19 작업 요청서 처리 — REQ-009 api_server Phase B `/auth/me` SSO smoke 차단(첫 로그인 후 `UserRepository.find_by_id`가 `NotFoundError` raise) 해소. `AuthenticateUseCase`에 JIT (Just-In-Time) auto-provisioning 블록 추가.

- **PR**: [#88 feat(auth): JIT user auto-provisioning — SSO 첫 로그인 시 users INSERT](https://github.com/billionaireahreum/Workflow_Automation/pull/88)
- **branch**: `feature/req-002-jit-user-provisioning` → base=`development`
- **commits**: `48b8308` (JIT 패치) + `bfff5b1` (spec 갱신) + 본 보고서 commit 예정

## 선행 의존

- PR #87 (조장 `cef92fa` split, `User` entity + `UserRepository` Port + storage 구현 6파일) — 2026-05-19 06:37 UTC development 머지 완료
- REQ-002 메인 4회차 sync로 흡수 (`5a16e7f`)

## 변경 (3 commits / 4 파일)

| commit | 파일 | 변경 |
|--------|------|------|
| `48b8308` | `modules/auth/application/use_cases/authenticate_use_case.py` | 생성자에 `user_repo: UserRepository` 추가 + `execute()` JIT 블록 |
| `48b8308` | `modules/auth/tests/conftest.py` | `InMemoryUserRepository(UserRepository)` 신규 + `user_repo` fixture |
| `48b8308` | `modules/auth/tests/unit/application/test_authenticate.py` | 기존 4건 fixture 흡수 + 신규 3건 JIT 시나리오 |
| `bfff5b1` | `docs/specs/REQ-002-auth.md` | §AuthenticateUseCase 설명/의존성에 `UserRepository` + JIT 동작 4단계 |

## JIT 블록 (use case `execute()`)

```python
google_sub: str = user_info["sub"]
user_id = uuid.uuid5(uuid.NAMESPACE_DNS, google_sub)

if await self._user_repo.find_by_id(user_id) is None:
    email: str = user_info["email"]
    await self._user_repo.create(
        user_id=user_id,
        email=email,
        name=user_info.get("name") or email.split("@")[0],
        role="User",
        department_id=None,
    )
```

## 셀프 리뷰 (박아름 4축 룰)

| 축 | 결과 |
|----|------|
| 클린 아키텍처 의존성 위반 | ✅ 위반 0건 (자기 모듈 + stdlib만, framework 직접 import 0건) |
| 타 모듈 import 문제 | ✅ 0건 (UserRepository는 PR #87로 development 머지된 자기 모듈 Port) |
| 스펙 정합 | ⚠️ §AuthenticateUseCase commit `bfff5b1`로 해소 / §UserRepository · §User entity 부재는 조장 후속 영역 (별도 카톡 알림) |
| SSOT | ✅ User/UserRepository SSOT = auth/domain (PR #87) |

## 검증 체크리스트 (조장 작업 요청서 §검증)

- [x] `pytest modules/auth/tests` — **34 passed (기존 31 + 신규 3, 회귀 0)**
- [x] `grep -rn "AuthenticateUseCase(" --include="*.py"` 결과 본 PR 외 호출자 0건
- [x] PR description에 "REQ-002 보강 — JIT user auto-provisioning" 명시
- [x] PR title 컨벤션 준수

## 신규 테스트 3건

| 테스트 | 시나리오 |
|--------|----------|
| `test_jit_creates_new_user_on_first_login` | 첫 로그인 → `users` INSERT (user_id/email/role/department_id/is_active 검증) |
| `test_existing_user_skips_create` | 재로그인 → 기존 user 유지 (`created_at` 변경 없음) |
| `test_jit_falls_back_to_email_prefix_when_name_missing` | `user_info`에 `name` 부재 시 email local-part로 fallback |

## Impact Assessment

| 영향 영역 | 평가 |
|----------|------|
| `modules/auth/tests/` | 신규 3건 + 기존 4건 fixture 흡수 — 회귀 0 |
| `modules/auth/application/` | 생성자 시그니처 1건 변경, 호출자 본 PR 외 0건 |
| `modules/storage/` | 변경 0건 (UserRepository Port 시그니처는 cef92fa 그대로) |
| `services/api_server/` | 후속 DI 주입 필요 (조장 PR #75 후속 commit) — 본 PR 영향 X |
| 다른 REQ 모듈 (ai_agent / nodes_graph / toolset 등) | 변경 0건 |

머지 자체 영향 = 0 (외부 호출자 없음). 머지 후 조장 PR #75 후속 commit으로 SSO smoke 완전 해소.

## 후속 영향 (REQ-009 측, 조장 본인 처리)

박아름 PR 머지 후 황대원이 PR #75에 후속 commit으로 처리:

1. `services/api_server/app/dependencies/auth.py` — `get_authenticate_use_case` provider에 `user_repo` 주입
2. `services/api_server/tests/test_routes_auth.py` — `test_login_*` fixture에 user_repo mock 추가
3. SSO smoke 재실행 (`/auth/login` → JWT → `/auth/me` → PermissionSource, NotFoundError 없음)

## 조장 후속 영역 (별도 PR 또는 PR #75 후속)

- `docs/specs/REQ-002-auth.md`에 §UserRepository Port / §User entity § 신설
- PR #87(cef92fa)로 코드는 development 머지됐으나 spec 미갱신 상태
- 박아름이 §AuthenticateUseCase 의존성에 `UserRepository` 추가했지만, spec 다른 §에서 Port 자체가 정의되어야 self-consistent

## 별도 트랙 (본 PR 범위 외)

- Workspace 도메인 검증 (Google `hd` 클레임 화이트리스트)
- Admin 승인 워크플로 (JIT 시 `role="Pending"` → 활성화)
- 기존 user 발견 시 이메일/이름 update

## 박아름 개발 환경 셋업 (5/19 추가)

`.venv`에 `auth` + `common_schemas` editable install 필수:

```powershell
uv pip install -e packages/common_schemas/python --python .venv/Scripts/python.exe
uv pip install -e modules/auth --python .venv/Scripts/python.exe
```
