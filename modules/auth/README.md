# auth

> REQ-002: 인증/인가, OAuth 연동, JWT 발급, 자격증명 암호화

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
from auth.domain.ports import SessionRepository, OAuthConnectionRepository, CipherPort
from auth.application.use_cases import (
    AuthenticateUseCase,
    IssueTokenUseCase,
    RefreshTokenUseCase,
    InjectCredentialUseCase,
)
```

## Public API

### domain/entities

| 클래스 | 주요 필드 |
|--------|----------|
| `Session` | session_id, user_id, session_hash, expires_at, is_revoked |
| `OAuthConnection` | oauth_id, user_id, service, access_token(암호화), refresh_token(암호화), scopes |

### domain/value_objects

| 클래스 | 주요 필드 |
|--------|----------|
| `TokenPair` | access_token, refresh_token, token_type, expires_in |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `PermissionResolver` | `resolve(user_id, role, department) → PermissionSource` | 사용자 권한 컨텍스트 생성 |
| `CredentialInjectionService` | `inject(credential_id) → PlaintextCredential` | 자격증명 복호화 + 자동 wipe |

### domain/ports (인터페이스 — 구현체는 `modules/storage`)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `SessionRepository` | create, find_by_hash, revoke, revoke_all_for_user | `storage/repositories/` |
| `OAuthConnectionRepository` | create, get_by_credential_id, get_active_for_user, update_tokens, revoke | `storage/repositories/` |
| `CipherPort` | encrypt(bytes)→bytes, decrypt(bytes)→bytes | `auth/adapters/cipher/` (자체 구현) |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `AuthenticateUseCase` | OAuth code → TokenPair | Google OAuth 코드 교환 + 세션 생성 |
| `IssueTokenUseCase` | session_hash → TokenPair | 기존 세션에서 JWT 발급 |
| `RefreshTokenUseCase` | refresh_token → TokenPair | 액세스 토큰 갱신 |
| `InjectCredentialUseCase` | credential_id → PlaintextCredential | 노드 실행 시 자격증명 복호화 |

### adapters/cipher

| 어댑터 | 설명 |
|--------|------|
| `AESGCMCipher` | AES-256-GCM 암호화 (CipherPort 구현) |
| `FernetCipher` | Fernet 대칭키 암호화 (CipherPort 구현) |

## 의존 관계

```
이 모듈 → common-schemas (PermissionSource, PlaintextCredential, RiskLevel)
이 모듈 ← ai-agent (CredentialInjectionService 호출)
이 모듈 ← api-server (AuthMiddleware, 라우터 인증)
이 모듈 ← storage (Repository 구현체 제공)
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `JWT_SECRET_KEY` | Y | JWT 서명 키 |
| `JWT_ALGORITHM` | N | 알고리즘 (기본: HS256) |
| `JWT_EXPIRY_SECONDS` | N | 액세스 토큰 만료 시간 (기본: 3600) |
| `ENCRYPTION_KEY` | Y | AES-GCM 마스터 키 |
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

제한 초과 시 429 Too Many Requests + `X-RateLimit-Remaining` 헤더.

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

## 외부 서비스 정책

- Google Workspace + Slack만 지원
- Microsoft (Outlook/OneDrive/Teams), Notion은 범위 외
- Google은 SSO 로그인 시 Workspace Scope 동시 동의 → `credential_id=google_default` 자동 등록
- Slack은 별도 OAuth 연결

## 테스트

```bash
pytest modules/auth/tests/
```
