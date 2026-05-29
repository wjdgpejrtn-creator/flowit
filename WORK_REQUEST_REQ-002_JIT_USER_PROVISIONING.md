# 작업 요청서 — REQ-002 보강: JIT User Auto-Provisioning

- **요청자**: 황대원 (조장, REQ-009 api_server 진행 중)
- **수신자**: 박아름 (REQ-002 auth 담당)
- **블로커**: REQ-009 Phase B `/auth/me` SSO smoke가 막힘 — JIT 미구현 시 첫 로그인 후 `UserRepository.find_by_id`가 `NotFoundError` raise
- **예상 작업량**: 1~2시간 (modules/auth 1파일 패치 + 테스트 1파일 갱신 + PR)
- **PR 분리 권고**: 별도 PR로 진행 (REQ-002 영역, REQ-009 PR #75와 독립)
- **기한**: REQ-009 Phase E(agents 라우터) 시작 전. 가급적 빠를수록 좋음.

---

## 배경

REQ-009 api_server에서 Google SSO를 통한 JWT 발급 흐름이 작동하려면, 첫 로그인 시 `users` 테이블에 신규 row가 INSERT되어야 한다. 현재 `AuthenticateUseCase`는 `sessions` + `oauth_connections`만 INSERT하고 `users`는 건드리지 않아, `/auth/me`에서 `UserRepository.find_by_id`가 NotFoundError를 raise한다.

일반적인 SSO 웹 서비스는 이 시점에 **JIT (Just-In-Time) auto-provisioning** 패턴을 사용한다 — OAuth code 교환 후 users 테이블에 없으면 즉시 INSERT.

선행 작업 완료(2026-05-18, PR #75 commit `cef92fa`):
- `modules/auth/domain/entities/user.py` — User entity 신설
- `modules/auth/domain/ports/user_repository.py` — UserRepository ABC 신설
- `modules/storage/orm/user_model.py` + `mappers/user_mapper.py` + `repositories/pg_user_repository.py` — 구현 신설

즉 `UserRepository` Port와 `PgUserRepository` 구현은 이미 있고, `AuthenticateUseCase`에 의존성만 추가하면 됨.

---

## JIT Auto-Provisioning 흐름 (참고)

```
1. OAuth code 교환 → Google에서 user info(sub, email, name, picture 등) 수신
2. user_id = uuid5(NAMESPACE_DNS, google_sub)  (기존 로직 그대로)
3. user_repo.find_by_id(user_id)
3-A. None → user_repo.create(user_id, email, name, role='User', department_id=None)  ← JIT
3-B. 존재 → 이메일/이름 변경 시 update (선택, 본 작업 범위 외 — 후속 PR 가능)
4. oauth_connections / sessions INSERT (기존 로직 그대로)
5. JWT 발급 (기존 로직 그대로)
```

### 변형 (본 작업 범위 외, 후속 가능)
- **Workspace 도메인 검증**: Google `hd` 클레임 화이트리스트
- **Admin 승인 워크플로**: JIT 시 `role='Pending'` → Admin 승인 후 활성화
- **이름/이메일 update**: 기존 user 발견 시 동기화

---

## 패치 대상 1: `modules/auth/application/use_cases/authenticate_use_case.py`

### 변경 시그니처

**Before**:
```python
def __init__(
    self,
    session_repo: SessionRepository,
    oauth_repo: OAuthConnectionRepository,
    cipher: CipherPort,
    google_oauth: OAuthClientPort,
    jwt_adapter: object,
) -> None:
```

**After**:
```python
def __init__(
    self,
    session_repo: SessionRepository,
    oauth_repo: OAuthConnectionRepository,
    user_repo: UserRepository,  # ← 추가
    cipher: CipherPort,
    google_oauth: OAuthClientPort,
    jwt_adapter: object,
) -> None:
```

### execute() 내부 패치

`user_id` 결정 직후, OAuth tokens 처리 전에 JIT 블록 삽입:

```python
async def execute(self, code: str) -> TokenPair:
    user_info = await self._google_oauth.exchange_code(code)
    google_sub: str = user_info["sub"]
    user_id = uuid.uuid5(uuid.NAMESPACE_DNS, google_sub)

    # ── JIT auto-provisioning ─────────────────────────────────────
    existing_user = await self._user_repo.find_by_id(user_id)
    if existing_user is None:
        await self._user_repo.create(
            user_id=user_id,
            email=user_info["email"],
            name=user_info.get("name") or user_info["email"].split("@")[0],
            role="User",
            department_id=None,
        )
    # ──────────────────────────────────────────────────────────────

    # 이하 기존 로직 그대로 (OAuth tokens 암호화, session 생성, JWT 발급)
```

### import 추가

```python
from ...domain.ports.user_repository import UserRepository
```

---

## 패치 대상 2: `modules/auth/tests/unit/application/test_authenticate.py`

기존 테스트가 `AuthenticateUseCase` 생성자 시그니처 변경으로 깨짐. mock 추가:

```python
# 기존 fixture에 user_repo mock 추가
user_repo = AsyncMock(spec=UserRepository)
user_repo.find_by_id = AsyncMock(return_value=None)  # 신규 사용자 시나리오
user_repo.create = AsyncMock()  # 호출 검증

# AuthenticateUseCase 생성에 user_repo 인자 추가
use_case = AuthenticateUseCase(
    session_repo=session_repo,
    oauth_repo=oauth_repo,
    user_repo=user_repo,  # ← 추가
    cipher=cipher,
    google_oauth=google_oauth,
    jwt_adapter=jwt_adapter,
)

# 신규 테스트 시나리오 (최소 2건 권장):
# (a) test_jit_creates_new_user — user_repo.find_by_id returns None → create 호출 검증
# (b) test_existing_user_skips_create — find_by_id returns User → create 미호출 검증
```

---

## 클린 아키텍처 / 크로스 모듈 의존성 검증

| 항목 | 결과 |
|------|------|
| `auth/application` → `auth/domain/ports.user_repository` import | ✅ 자기 모듈 도메인 Port (CLAUDE.md 의존성 방향 규칙 정합) |
| 신규 외부 모듈 의존 추가 | 0건 — UserRepository는 이미 PR #75에서 신설됨 |
| 의존성 사이클 | 없음 (auth → storage 역의존 0건, grep 검증 완료) |
| ADR-0012 v3 정합 | ✅ Port는 auth/domain, 구현은 storage/repositories |

---

## 후속 영향 (REQ-009 측, 본인 처리)

박아름 PR이 머지되면 황대원이 본 PR #75에 후속 commit으로 처리:

1. **`services/api_server/app/dependencies/auth.py`** — `get_authenticate_use_case`에 `user_repo` provider 주입
   ```python
   def get_authenticate_use_case(
       session_repo: SessionRepository = Depends(get_session_repository),
       oauth_repo: OAuthConnectionRepository = Depends(get_oauth_repository),
       user_repo: UserRepository = Depends(get_user_repository),  # ← 추가
       cipher: CipherPort = Depends(get_cipher),
       google_oauth: OAuthClientPort = Depends(get_google_oauth),
       jwt_adapter: JWTAdapter = Depends(get_jwt_adapter),
   ) -> AuthenticateUseCase:
       return AuthenticateUseCase(
           session_repo=session_repo,
           oauth_repo=oauth_repo,
           user_repo=user_repo,  # ← 추가
           cipher=cipher,
           google_oauth=google_oauth,
           jwt_adapter=jwt_adapter,
       )
   ```

2. **`services/api_server/tests/test_routes_auth.py`** — `test_login_*` fixture에 user_repo mock 추가 (생성자 시그니처 일치).

3. **SSO smoke 재실행** — `/auth/login` 또는 `/auth/callback` → JWT 발급 → `/auth/me` → PermissionSource 반환 (NotFoundError 없음).

---

## 검증 체크리스트 (박아름 PR)

- [ ] `pytest modules/auth/tests` — 신규 JIT 테스트 2건 포함 회귀 통과
- [ ] `AuthenticateUseCase(session_repo, oauth_repo, user_repo, cipher, google_oauth, jwt_adapter)` 생성자 변경 외 다른 모듈 영향 없음 (`grep -rn "AuthenticateUseCase(" --include="*.py"` 결과 본 PR 외 변경 0건이어야 함)
- [ ] PR description에 "REQ-002 보강 — JIT user auto-provisioning" 명시
- [ ] PR title 예시: `feat(auth): JIT user auto-provisioning — SSO 첫 로그인 시 users INSERT`

---

## 참고 파일 절대 경로

- `C:\Users\user\Documents\GitHub\Workflow_Automation\modules\auth\application\use_cases\authenticate_use_case.py` (패치 대상)
- `C:\Users\user\Documents\GitHub\Workflow_Automation\modules\auth\tests\unit\application\test_authenticate.py` (테스트 갱신)
- `C:\Users\user\Documents\GitHub\Workflow_Automation\modules\auth\domain\ports\user_repository.py` (Port 시그니처 참조)
- `C:\Users\user\Documents\GitHub\Workflow_Automation\modules\auth\domain\entities\user.py` (User entity 참조)
- `C:\Users\user\Documents\GitHub\Workflow_Automation\modules\storage\repositories\pg_user_repository.py` (구현 참조 — 본 PR 영향 없음)
- `C:\Users\user\Documents\GitHub\Workflow_Automation\database\schemas\001_core.sql` (users 테이블 schema)

---

## 본 PR(REQ-009)에서의 일시 대처

박아름 PR 머지 전까지 REQ-009는 다음과 같이 진행:
- Phase C (nodes catalog), Phase D (workflows CRUD) — user 의존 적음, JIT 없이 진행 가능. 단 `/auth/me` 의존 라우터는 staging smoke 한계.
- Phase B `/auth/me` SSO smoke — 박아름 PR 머지 후 통합 검증

황대원은 본 PR description(`#75`)에 본 작업 요청서 link + dependency 표기.
