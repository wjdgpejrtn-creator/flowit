# auth

> REQ-002: 인증/인가, OAuth 연동, JWT 발급, 자격증명 암호화
>
> 구현 명세 → [`docs/specs/REQ-002-auth.md`](../../docs/specs/REQ-002-auth.md)

## 설치

```bash
pip install -e modules/auth
pip install -e "modules/auth[dev]"
```

## Quick Start

```python
from auth.domain.services import PermissionResolver, CredentialInjectionService
from auth.domain.entities import Session, OAuthConnection
from auth.domain.value_objects import TokenPair
from auth.domain.ports import SessionRepository, OAuthConnectionRepository, CipherPort, OAuthClientPort
from auth.application.use_cases import (
    AuthenticateUseCase,
    IssueTokenUseCase,
    RefreshTokenUseCase,
    InjectCredentialUseCase,
)
```

## Public API

### domain/entities

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `Session` | `session_id: UUID`, `user_id: UUID`, `session_hash: str`, `expires_at: datetime`, `is_revoked: bool`, `device_info: Optional[str]` | JWT 세션. `is_expired() → bool`, `revoke() → None` 메서드 제공 |
| `OAuthConnection` | `oauth_id: UUID`, `user_id: UUID`, `service: Literal["google","slack"]`, `credential_id: UUID`, `access_token_encrypted: bytes`, `refresh_token_encrypted: Optional[bytes]`, `scopes: list[str]`, `is_active: bool` | 외부 서비스 OAuth 연결. `revoke() → None` 메서드 제공 |

### domain/value_objects

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `TokenPair` | `access_token: str`, `refresh_token: str`, `token_type: Literal["Bearer"]`, `expires_in: int` | JWT 토큰 쌍 (frozen) |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `PermissionResolver` | `resolve(user_id: UUID, role: Literal["User","Admin"], department_id: UUID, session_id: UUID, current_workflow_id: Optional[UUID], current_skill_id: Optional[UUID]) → PermissionSource` | 6차원 권한 모델 기반 컨텍스트 생성 |
| `CredentialInjectionService` | `async inject(credential_id: UUID, node_id: UUID) → PlaintextCredential` | 노드 실행 시 자격증명 복호화. `NodeDefinitionRepository.get_by_id(node_id)` → `risk_level`, `required_connections`, `service_type` 필드 접근 후 검증 (H-4 합의) |

### domain/ports (인터페이스 — 구현체는 `modules/storage`)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `SessionRepository` | `async create(user_id: UUID, session_hash: str, **kwargs) → Session` | `storage/repositories/` |
| | `async find_by_hash(session_hash: str) → Optional[Session]` | |
| | `async revoke(session_id: UUID) → None` | |
| | `async revoke_all_for_user(user_id: UUID) → int` | |
| `OAuthConnectionRepository` | `async create(user_id: UUID, service: str, tokens: dict) → OAuthConnection` | `storage/repositories/` |
| | `async get_by_credential_id(credential_id: UUID) → Optional[OAuthConnection]` | |
| | `async get_active_for_user(user_id: UUID, service: str) → Optional[OAuthConnection]` | |
| | `async update_tokens(credential_id: UUID, new_tokens: dict) → None` | |
| | `async revoke(credential_id: UUID) → None` | |
| `CipherPort` | `encrypt(plaintext: bytes) → bytes`, `decrypt(ciphertext: bytes) → bytes` | `auth/adapters/cipher/` (자체 구현) |
| `OAuthClientPort` | `async exchange_code(code: str) → dict`, `async refresh_access_token(refresh_token: str) → dict`, `async get_user_info(access_token: str) → dict` | `auth/adapters/oauth/` (자체 구현) |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `AuthenticateUseCase` | `OAuth code, redirect_uri → TokenPair` | Google OAuth 코드 교환 + 세션 생성 |
| `IssueTokenUseCase` | `session_hash: str → TokenPair` | 기존 세션에서 JWT 발급 |
| `RefreshTokenUseCase` | `refresh_token: str → TokenPair` | 액세스 토큰 갱신 (Refresh Token Rotation 적용) |
| `InjectCredentialUseCase` | `credential_id: UUID, node_id: UUID → PlaintextCredential` | 노드 실행 시 자격증명 복호화 |

### adapters/cipher

| 어댑터 | 설명 |
|--------|------|
| `AESGCMCipher` | AES-256-GCM 암호화 (`CipherPort` 구현). `database/src/protocols.py`의 `BaseCipher(typing.Protocol)`도 구조적 만족 (ADR-0004) |
| `FernetCipher` | Fernet 대칭키 암호화 (`CipherPort` 구현) |

### adapters/oauth

| 어댑터 | 설명 |
|--------|------|
| `GoogleOAuthClient` | Google OAuth 2.0 클라이언트 (`OAuthClientPort` 구현). 코드 교환, 토큰 갱신, 사용자 정보 조회 |

## 의존 관계

```
Upstream (이 모듈이 의존):
  ├── common-schemas (REQ-012)
  │     └── PermissionSource, PlaintextCredential, RiskLevel, ErrorCode
  └── nodes-graph (REQ-003)
        └── NodeDefinitionRepository ABC (CredentialInjectionService가 get_by_id 후 필드 접근)

Downstream (이 모듈에 의존):
  ├── ai-agent (REQ-004)      → CredentialInjectionService 호출
  ├── api-server (REQ-009)    → AuthMiddleware, JWT 검증
  ├── execution-engine (REQ-007) → InjectCredentialUseCase 호출
  └── storage (REQ-008)       → SessionRepository, OAuthConnectionRepository 구현체 제공
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `JWT_SECRET_KEY` | Y | JWT 서명 키 (HS256) |
| `JWT_ALGORITHM` | N | 알고리즘 (기본: HS256) |
| `JWT_EXPIRY_SECONDS` | N | 액세스 토큰 만료 시간 (기본: 3600) |
| `ENCRYPTION_KEY` | Y | AES-256-GCM 마스터 키 (32바이트, base64) |
| `GOOGLE_CLIENT_ID` | Y | Google OAuth 클라이언트 ID |
| `GOOGLE_CLIENT_SECRET` | Y | Google OAuth 클라이언트 시크릿 |

## 6차원 권한 모델

| 차원 | 설명 | 검증 대상 |
|------|------|----------|
| Role (RBAC) | User / Admin | 관리자 전용 엔드포인트 |
| Ownership | 리소스 소유자 | workflows, skills, agent_memories(private) |
| Resource Scope | Private / Team / Public | workflows, skills |
| Department | 같은 부서 사용자만 Team 접근 | workflows(team), skills(team) |
| Node Risk Level | Low / Medium / High / Restricted | node_definitions |
| Memory Scope | private / team / public | agent_memories |

## Rate Limiting

| API 유형 | 제한 |
|---------|------|
| 일반 API | 분당 60회 |
| LLM 호출 API | 분당 10회 |
| OAuth 콜백 API | 분당 5회 |

## 에러 코드

| 코드 | 의미 | HTTP |
|------|------|------|
| E-AUTH-001 | OAuth state 검증 실패 (CSRF) | 400 |
| E-AUTH-003 | JWT 만료 | 401 |
| E-AUTH-005 | Refresh Token 무효/폐기 | 401 |
| E-AUTH-006 | Refresh Token 재사용 감지 | 401 |
| E-PERM-001 | 권한 없음 (RBAC) | 403 |
| E-PERM-002 | Ownership 위반 | 403 |
| E-PERM-004 | Risk Level 차단 | 403 |
| E-MEM-001 | Agent Memory Scope 위반 | 403 |
| E-CRED-001 | Credential Injection 실패 | 401 |
| E-CRED-002 | 외부 서비스 토큰 refresh 실패 | 401 |

## 테스트

```bash
pytest modules/auth/tests/
```
