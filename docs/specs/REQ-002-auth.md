# REQ-002 Auth-Security — 구현 명세

- **담당자**: 박아름
- **작성일**: 2026-05-05
- **참조**: `docs/class_diagram_resolution_proposal.md` (H-2, H-3, H-4 확정), `docs/context/adr/ADR-0004`, `ADR-0005`

---

## common_schemas에서 import할 클래스

| 클래스 | 소스 모듈 | 용도 |
|--------|-----------|------|
| `PermissionSource` | `common_schemas.security` | 6차원 권한 모델의 컨텍스트 VO. PermissionResolver가 생성하여 반환 |
| `PlaintextCredential` | `common_schemas.security` | 복호화된 자격증명을 담는 VO. CredentialInjectionService 반환 타입 |
| `RiskLevel` | `common_schemas.enums` | 노드 위험 등급 열거형. CredentialInjectionService에서 위험 수준 검증 시 사용 |
| `ErrorCode` | `common_schemas.enums` | 권한/인증 관련 에러 코드 (E_PERMISSION_DENIED, E_MISSING_CONNECTION) |
| `ValidationError` | `common_schemas.exceptions` | 입력 검증 실패 시 raise |
| `AuthorizationError` | `common_schemas.exceptions` | 권한 검증 실패 시 raise |
| `NotFoundError` | `common_schemas.exceptions` | 세션/연결 미발견 시 raise |

```python
from common_schemas import PermissionSource, PlaintextCredential
from common_schemas.enums import RiskLevel, ErrorCode
from common_schemas.exceptions import ValidationError, AuthorizationError, NotFoundError
```

---

## 이 모듈에서 구현할 클래스

### Domain Layer (`modules/auth/domain/`)

#### entities/session.py — `Session`

| 필드 | 타입 | 설명 |
|------|------|------|
| `session_id` | `UUID` | PK |
| `user_id` | `UUID` | 세션 소유자 |
| `session_hash` | `str` | SHA-256 해시 (조회 키) |
| `expires_at` | `datetime` | 만료 시점 |
| `is_revoked` | `bool` | 폐기 여부 (default=False) |
| `created_at` | `datetime` | 생성 시점 |
| `device_info` | `Optional[str]` | 디바이스 메타 (향후 확장) |

메서드:
- `is_expired() -> bool` — 현재 시각 기준 만료 여부
- `revoke() -> None` — `is_revoked = True` 설정

---

#### entities/oauth_connection.py — `OAuthConnection`

| 필드 | 타입 | 설명 |
|------|------|------|
| `oauth_id` | `UUID` | PK |
| `user_id` | `UUID` | 소유자 |
| `service` | `Literal["google", "slack"]` | 외부 서비스 종류 |
| `credential_id` | `UUID` | PlaintextCredential 참조 키 |
| `access_token_encrypted` | `bytes` | 암호화된 액세스 토큰 |
| `refresh_token_encrypted` | `Optional[bytes]` | 암호화된 리프레시 토큰 |
| `scopes` | `list[str]` | 부여된 OAuth 스코프 |
| `is_active` | `bool` | 활성 여부 |
| `connected_at` | `datetime` | 연결 시점 |
| `last_refreshed_at` | `Optional[datetime]` | 마지막 토큰 갱신 시점 |

메서드:
- `revoke() -> None` — `is_active = False`

---

#### value_objects/token_pair.py — `TokenPair`

| 필드 | 타입 | 설명 |
|------|------|------|
| `access_token` | `str` | JWT 액세스 토큰 |
| `refresh_token` | `str` | 리프레시 토큰 |
| `token_type` | `Literal["Bearer"]` | 토큰 타입 |
| `expires_in` | `int` | 만료까지 남은 초 |

Pydantic `frozen=True`.

---

#### ports/cipher_port.py — `CipherPort` (ABC)

```python
from abc import ABC, abstractmethod

class CipherPort(ABC):
    """REQ-002 소유. 대칭키 암호화 인터페이스.
    
    REQ-001 Database는 이 포트를 직접 import하지 않는다.
    대신 database/src/protocols.py의 BaseCipher(typing.Protocol)을 사용한다.
    DI composition root에서 AESGCMCipher가 양쪽을 모두 만족시킨다.
    (ADR-0004 참조)
    """
    
    @abstractmethod
    def encrypt(self, plaintext: bytes) -> bytes:
        """평문 바이트를 암호화하여 반환."""
        ...
    
    @abstractmethod
    def decrypt(self, ciphertext: bytes) -> bytes:
        """암호문 바이트를 복호화하여 반환."""
        ...
```

**시그니처 확정**: `bytes → bytes` (H-2 합의, `str` 아님)

---

#### ports/session_repository.py — `SessionRepository` (ABC)

```python
from abc import ABC, abstractmethod
from uuid import UUID

class SessionRepository(ABC):
    """세션 저장소 인터페이스. 구현은 REQ-001/REQ-008(storage)이 담당."""
    
    @abstractmethod
    async def create(self, user_id: UUID, session_hash: str, **kwargs) -> Session:
        """새 세션 생성. kwargs로 device_info 등 확장 가능."""
        ...
    
    @abstractmethod
    async def find_by_hash(self, session_hash: str) -> Optional[Session]:
        """해시값으로 세션 조회. 없으면 None."""
        ...
    
    @abstractmethod
    async def revoke(self, session_id: UUID) -> None:
        """단일 세션 폐기."""
        ...
    
    @abstractmethod
    async def revoke_all_for_user(self, user_id: UUID) -> int:
        """특정 사용자의 모든 세션 폐기. 폐기된 건수 반환 (감사 로깅용)."""
        ...
```

---

#### ports/oauth_connection_repository.py — `OAuthConnectionRepository` (ABC)

```python
from abc import ABC, abstractmethod
from uuid import UUID

class OAuthConnectionRepository(ABC):
    """OAuth 연결 저장소 인터페이스. 구현은 REQ-001/REQ-008(storage)이 담당."""
    
    @abstractmethod
    async def create(self, user_id: UUID, service: str, tokens: dict) -> OAuthConnection:
        """새 OAuth 연결 생성."""
        ...
    
    @abstractmethod
    async def get_by_credential_id(self, credential_id: UUID) -> Optional[OAuthConnection]:
        """credential_id로 연결 조회."""
        ...
    
    @abstractmethod
    async def get_active_for_user(self, user_id: UUID, service: str) -> Optional[OAuthConnection]:
        """특정 사용자의 활성 연결 조회 (서비스별 필터)."""
        ...
    
    @abstractmethod
    async def update_tokens(self, credential_id: UUID, new_tokens: dict) -> None:
        """암호화된 토큰 갱신. new_tokens = {access_token_encrypted, refresh_token_encrypted?}"""
        ...
    
    @abstractmethod
    async def revoke(self, credential_id: UUID) -> None:
        """연결 폐기 (is_active=False)."""
        ...
```

---

#### services/permission_resolver.py — `PermissionResolver`

```python
class PermissionResolver:
    """사용자 권한 컨텍스트를 PermissionSource VO로 생성."""
    
    def resolve(
        self,
        user_id: UUID,
        role: Literal["User", "team_manager", "company_manager", "Admin"],
        department_id: UUID,
        session_id: UUID,
        current_workflow_id: Optional[UUID] = None,
        current_skill_id: Optional[UUID] = None,
    ) -> PermissionSource:
        """6차원 권한 모델에 따라 granted_scopes, risk_ceiling 결정 후 반환."""
        ...
```

---

#### services/credential_injection_service.py — `CredentialInjectionService`

```python
class CredentialInjectionService:
    """노드 실행 시 자격증명을 복호화하여 주입 (ADR-0018 Decision 5·6).
    
    H-4 합의: NodeDefinitionRepository.get_by_id() 호출 후 필드 접근으로
    risk_level, required_connections, service_type을 확인한다.
    `credentials` 테이블을 해결 SSOT로 두고 credential_kind로 분기한다.
    """
    
    def __init__(
        self,
        cipher: CipherPort,
        oauth_repo: OAuthConnectionRepository,
        node_def_repo: NodeDefinitionRepository,  # REQ-003에서 정의한 ABC
        credential_repo: CredentialRepository,
    ):
        ...
    
    async def inject(self, credential_id: UUID, node_id: UUID) -> PlaintextCredential:
        """
        1. node_def_repo.get_by_id(node_id) → NodeDefinition (없으면 NotFoundError)
        2. node_def.risk_level == RESTRICTED이면 AuthorizationError
        3. credential_repo.get_by_id(credential_id) → Credential
           (없거나 is_active=False이면 NotFoundError)
        4. credential.credential_kind 분기:
           - oauth_token: oauth_repo.get_by_credential_id로 enrich →
             required_connections ↔ conn.service 검증 → decrypt(access_token_encrypted)
           - api_key 등: decrypt(credential.encrypted_data) 직접 (service-match 비적용 —
             credentials에 service 컬럼 없음, 검증은 OAuth 스코핑 전용)
        5. PlaintextCredential 생성 후 반환
        
        주의: 호출측은 사용 후 반드시 credential.wipe() 호출.
        """
        ...
```

**service-match 정책 (의도적 — 보안 판단)**: `required_connections ↔ service` 검증은 `oauth_token` credential에만 적용한다. OAuth access token은 특정 provider 스코프에 묶여 있어 provider 불일치 주입(google 토큰을 slack 노드에) 차단이 필요하다. 반면 `api_key`는 워크플로우 작성자가 `node.credential_id`로 명시 선택하는 author-scoped 자원이라 provider 스코핑 대상이 아니다 — `credentials`에 service 컬럼이 없는 것은 이 정책의 결과이지 원인이 아니다. 두 경로 모두 RESTRICTED 위험도 게이트 + credential 활성 검증은 동일 적용된다. (api_key를 노드 service에 묶고 싶으면 `Credential.metadata["service"]` 기반 검증을 후속 도입할 수 있다 — 현재는 미적용.)

---

### Application Layer (`modules/auth/application/`)

#### use_cases/authenticate_use_case.py — `AuthenticateUseCase`

| Input | Output | 설명 |
|-------|--------|------|
| OAuth authorization code, redirect_uri | `TokenPair` | Google OAuth 코드 교환 → **users 테이블 JIT auto-provisioning (없으면 INSERT)** → `credentials` row 생성(`oauth_token` kind) → `oauth_connections` 연결 → 세션 생성 → JWT 발급 |

의존성: `SessionRepository`, `OAuthConnectionRepository`, `UserRepository`, `CredentialRepository`, `CipherPort`, 외부 Google OAuth 클라이언트

`CredentialRepository`(PR #99): `oauth_connections.credential_id`는 `credentials` 테이블 FK(NOT NULL UNIQUE)이므로, OAuth connection을 만들기 전에 `credentials` row를 먼저 생성하고 그 `credential_id`로 연결한다. 재로그인 시 `credential_repo.update_data` + `oauth_repo.update_tokens`를 같은 트랜잭션에서 호출. (토큰이 `credentials.encrypted_data`와 `oauth_connections.access_token_encrypted` 양쪽에 저장되는 스키마 redundancy는 알려진 부채 — 후속 ADR에서 SSOT 일원화 검토.)

JIT auto-provisioning 동작:
1. `user_id = uuid5(NAMESPACE_DNS, google_sub)` (결정적 UUID 파생)
2. `user_repo.find_by_id(user_id)` 조회 — `None`이면 `user_repo.create(user_id, email, name, role="User", department_id=None)` 호출
3. `name`이 `user_info`에 없으면 email local-part로 fallback
4. 기존 user 발견 시 재생성 안 함 (created_at 보존)

후속 확장 (별도 PR): 이메일/이름 동기화 update, Workspace 도메인 검증 (`hd` 클레임), Admin 승인 워크플로 (`role="Pending"`)

---

#### use_cases/issue_token_use_case.py — `IssueTokenUseCase`

| Input | Output | 설명 |
|-------|--------|------|
| `session_hash: str` | `TokenPair` | 기존 유효 세션에서 새 JWT 발급 |

의존성: `SessionRepository`

---

#### use_cases/refresh_token_use_case.py — `RefreshTokenUseCase`

| Input | Output | 설명 |
|-------|--------|------|
| `refresh_token: str` | `TokenPair` | 리프레시 토큰으로 액세스 토큰 갱신 |

의존성: `SessionRepository`  
보안: Refresh Token Rotation 적용 — 재사용 감지 시 전체 세션 폐기 (E-AUTH-006)

---

#### use_cases/inject_credential_use_case.py — `InjectCredentialUseCase`

| Input | Output | 설명 |
|-------|--------|------|
| `credential_id: UUID`, `node_id: UUID` | `PlaintextCredential` | 노드 실행 시 자격증명 복호화 |

의존성: `CredentialInjectionService`

---

### Infrastructure/Adapter Layer (`modules/auth/adapters/`)

#### cipher/aes_gcm.py — `AESGCMCipher`

```python
class AESGCMCipher(CipherPort):
    """AES-256-GCM 암호화 구현체.
    
    - 12바이트 랜덤 nonce 자동 생성 (매 암호화 시 새 nonce)
    - 암호문 형식: nonce(12) + ciphertext + tag(16)
    - 키: 환경변수 ENCRYPTION_KEY에서 로드 (32바이트)
    
    이 클래스는 동시에 database/src/protocols.py의 BaseCipher(typing.Protocol)도
    구조적으로 만족한다 (ADR-0004).
    """
    
    def __init__(self, key: bytes):
        assert len(key) == 32, "AES-256 requires 32-byte key"
        self._key = key
    
    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, ciphertext: bytes) -> bytes: ...
```

---

#### cipher/fernet_cipher.py — `FernetCipher`

```python
class FernetCipher(CipherPort):
    """Fernet 대칭키 암호화 구현체.
    
    - cryptography 라이브러리의 Fernet 사용
    - 키: URL-safe base64 인코딩된 32바이트
    - 용도: AES-GCM 대비 간편한 암호화 (비핵심 데이터)
    """
    
    def __init__(self, key: bytes): ...
    def encrypt(self, plaintext: bytes) -> bytes: ...
    def decrypt(self, ciphertext: bytes) -> bytes: ...
```

---

#### oauth/google_oauth_client.py — `GoogleOAuthClient`

```python
class GoogleOAuthClient:
    """Google OAuth 2.0 코드 교환 + 토큰 갱신 어댑터."""
    
    async def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """Authorization code → access_token, refresh_token, id_token"""
        ...
    
    async def refresh_access_token(self, refresh_token: str) -> dict:
        """Refresh token → new access_token"""
        ...
    
    async def get_user_info(self, access_token: str) -> dict:
        """UserInfo endpoint에서 사용자 정보 조회"""
        ...
```

---

## 합의된 변경사항 (클래스 다이어그램 교차분석)

| 이슈 ID | 합의 내용 | 영향 |
|---------|-----------|------|
| **H-2** | REQ-002가 cipher 소유. encrypt/decrypt 시그니처 `bytes→bytes` 통일. 구현체명 `AESGCMCipher` 확정. REQ-001의 `EncryptionStrategy` 삭제 | REQ-001은 DI로 cipher를 주입받음 |
| **H-3** | REQ-002의 ABC가 계약 기준. REQ-001 구현체가 메서드명/시그니처를 맞춤 | 반환 타입: ORM 모델이 아닌 도메인 엔티티 |
| **H-4** | NodeDefinitionRepository에 별도 메서드 추가 안 함. `get_by_id()` 후 필드 접근으로 risk_level/required_connections/service_type 확인 | CredentialInjectionService 구현 방식 확정 |
| **ADR-0004** | `database/src/protocols.py`에 `BaseCipher`를 `typing.Protocol`로 정의. REQ-002 구현체가 이 Protocol도 구조적으로 만족 | DI composition root에서 양쪽 연결 |
| **ADR-0005** | SessionRepository/OAuthConnectionRepository H-3 시그니처 계약 확정. 모든 메서드 async | REQ-001 구현체 리팩터링 완료 |

---

## 의존성 관계

```
Upstream (이 모듈이 의존):
  ├── packages/common_schemas (REQ-012)
  │     └── PermissionSource, PlaintextCredential, RiskLevel, ErrorCode
  └── modules/nodes_graph (REQ-003)
        └── NodeDefinitionRepository ABC (CredentialInjectionService에서 사용)

Downstream (이 모듈에 의존):
  ├── modules/ai_agent (REQ-004)
  │     └── CredentialInjectionService 호출 (노드 실행 전 자격증명 주입)
  ├── services/api_server (REQ-009)
  │     └── AuthMiddleware, JWT 검증, 라우터 인증
  ├── modules/storage (REQ-008) / database (REQ-001)
  │     └── SessionRepository, OAuthConnectionRepository 구현체 제공
  └── services/execution_engine (REQ-007)
        └── 노드 실행 시 InjectCredentialUseCase 호출
```

---

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `JWT_SECRET_KEY` | Y | JWT 서명 키 (HS256) |
| `JWT_ALGORITHM` | N | 기본값: `"HS256"` |
| `JWT_EXPIRY_SECONDS` | N | 액세스 토큰 만료 (기본: 3600초) |
| `ENCRYPTION_KEY` | Y | AES-256-GCM 마스터 키 (32바이트, base64 인코딩) |
| `GOOGLE_CLIENT_ID` | Y | Google OAuth 클라이언트 ID |
| `GOOGLE_CLIENT_SECRET` | Y | Google OAuth 클라이언트 시크릿 |

---

## 디렉토리 구조 (목표)

```
modules/auth/
├── __init__.py
├── domain/
│   ├── entities/
│   │   ├── session.py              # Session
│   │   └── oauth_connection.py     # OAuthConnection
│   ├── value_objects/
│   │   └── token_pair.py           # TokenPair
│   ├── services/
│   │   ├── permission_resolver.py  # PermissionResolver
│   │   └── credential_injection_service.py  # CredentialInjectionService
│   └── ports/
│       ├── cipher_port.py          # CipherPort (ABC)
│       ├── session_repository.py   # SessionRepository (ABC)
│       └── oauth_connection_repository.py  # OAuthConnectionRepository (ABC)
├── application/
│   └── use_cases/
│       ├── authenticate_use_case.py
│       ├── issue_token_use_case.py
│       ├── refresh_token_use_case.py
│       └── inject_credential_use_case.py
├── adapters/
│   ├── cipher/
│   │   ├── aes_gcm.py             # AESGCMCipher
│   │   └── fernet_cipher.py       # FernetCipher
│   └── oauth/
│       └── google_oauth_client.py  # GoogleOAuthClient
└── tests/
    ├── test_session.py
    ├── test_credential_injection.py
    ├── test_cipher.py
    └── test_permission_resolver.py
```
