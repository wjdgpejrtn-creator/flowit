# REQ-002 Auth 모듈 구현 Plan

**브랜치**: `feature/req-002-auth`  
**담당자**: 박아름  
**작성일**: 2026-05-06  
**참조 스펙**: `docs/specs/REQ-002-auth.md`

---

## 구현해야 하는 클래스 목록

### Domain Layer

| 클래스 | 파일 경로 | 상태 |
|--------|-----------|------|
| `Session` | `domain/entities/session.py` | ✅ 완료 |
| `OAuthConnection` | `domain/entities/oauth_connection.py` | ✅ 완료 |
| `TokenPair` | `domain/value_objects/token_pair.py` | ✅ 완료 |
| `CipherPort` (ABC) | `domain/ports/cipher_port.py` | ✅ 완료 |
| `OAuthClientPort` (ABC) | `domain/ports/oauth_client_port.py` | ✅ 완료 (리뷰 반영 신설) |
| `SessionRepository` (ABC) | `domain/ports/session_repository.py` | ✅ 완료 |
| `OAuthConnectionRepository` (ABC) | `domain/ports/oauth_repository.py` | ✅ 완료 |
| `PermissionResolver` | `domain/services/permission_resolver.py` | ✅ 완료 |
| `CredentialInjectionService` | `domain/services/credential_injection.py` | ✅ 완료 (node_id 파라미터는 REQ-003 완성 후 확장) |

### Application Layer

| 클래스 | 파일 경로 | 상태 |
|--------|-----------|------|
| `AuthenticateUseCase` | `application/use_cases/authenticate.py` | ✅ 완료 |
| `IssueTokenUseCase` | `application/use_cases/issue_token.py` | ✅ 완료 |
| `RefreshTokenUseCase` | `application/use_cases/refresh_token.py` | ✅ 완료 |
| `InjectCredentialUseCase` | `application/use_cases/inject_credential.py` | ✅ 완료 |

### Adapter Layer

| 클래스 | 파일 경로 | 상태 |
|--------|-----------|------|
| `AESGCMCipher` | `adapters/cipher/aes_gcm.py` | ✅ 완료 (`CipherPort` 직접 구현) |
| `FernetCipher` | `adapters/cipher/fernet_cipher.py` | ✅ 완료 (`CipherPort` 직접 구현) |
| ~~`BaseCipher`~~ | ~~`adapters/cipher/base_cipher.py`~~ | 🗑️ 삭제 (빈 중간 클래스, 리뷰 반영) |
| `GoogleOAuthClient` | `adapters/oauth/google_oauth_client.py` | ✅ 완료 (`OAuthClientPort` 구현) |
| ~~`GoogleOAuthAdapter`~~ | ~~`adapters/google_oauth.py`~~ | 🗑️ 삭제 (중복 어댑터, 리뷰 반영) |
| `JWTAdapter` | `adapters/jwt_adapter.py` | ✅ 완료 |
| `AuthMiddleware` | `adapters/middleware.py` | ✅ 완료 |

---

## 사용해야 하는 클래스 목록 (common_schemas import)

| 클래스 | import 경로 | 사용처 |
|--------|-------------|--------|
| `PermissionSource` | `common_schemas.security` | `PermissionResolver.resolve()` 반환 타입 |
| `PlaintextCredential` | `common_schemas.security` | `CredentialInjectionService.inject()` 반환 타입 |
| `RiskLevel` | `common_schemas.enums` | `CredentialInjectionService` 위험 수준 검증 |
| `ErrorCode` | `common_schemas.enums` | 에러 코드 참조 |
| `AuthorizationError` | `common_schemas.exceptions` | 인증/인가 실패 시 raise |
| `NotFoundError` | `common_schemas.exceptions` | 세션/연결 미발견 시 raise |
| `ValidationError` | `common_schemas.exceptions` | 입력 검증 실패 시 raise |

---

## 테스트 목록

### unit/domain

| 테스트 파일 | 테스트 대상 | 상태 |
|-------------|-------------|------|
| `test_session.py` | `Session.is_expired()`, `revoke()`, `device_info` (스펙 기준 재정렬) | ✅ 완료 |
| `test_permission_resolver.py` | `PermissionResolver.resolve()` Admin/User 분기 | ✅ 완료 |
| `test_credential_injection.py` | `CredentialInjectionService.inject()` 복호화/폐기 처리 | ✅ 완료 |

### unit/application

| 테스트 파일 | 테스트 대상 | 상태 |
|-------------|-------------|------|
| `test_issue_token.py` | `IssueTokenUseCase` 정상/만료/폐기 분기 | ✅ 완료 |
| `test_refresh_token.py` | `RefreshTokenUseCase` 정상/잘못된 타입/폐기 분기 | ✅ 완료 |
| `test_inject_credential.py` | `InjectCredentialUseCase` 정상/폐기/미존재 분기 | ✅ 완료 |
| `test_authenticate.py` | `AuthenticateUseCase` 신규/재인증/토큰 암호화 검증 | ✅ 완료 |

### integration (추후)

| 테스트 파일 | 테스트 대상 | 상태 |
|-------------|-------------|------|
| `test_aesgcm_cipher.py` | `AESGCMCipher` 실제 암복호화 | ⬜ 미작성 |
| `test_jwt_adapter.py` | `JWTAdapter` 실제 인코딩/디코딩 | ⬜ 미작성 |

---

## 구현 순서 (Clean Architecture 원칙)

```
1. common_schemas 타입 확인 (SSOT 기반)
2. domain/entities → domain/value_objects
3. domain/ports (ABC 정의)
4. domain/services (Port에만 의존)
5. application/use_cases (Port + domain/services 조합)
6. adapters (Port 구현체)
7. tests/unit/domain → tests/unit/application → tests/integration
```

---

## 미결 사항 (Future Work)

| 항목 | 이유 | 해결 조건 |
|------|------|-----------|
| ~~`CredentialInjectionService`에 `node_id` 파라미터 추가~~ | ~~REQ-003 `NodeDefinitionRepository` ABC 미완성~~ | ✅ 완료 (2026-05-07, 스펙 기준 재정렬 PR #19) |
| integration 테스트 작성 | 실제 암복호화/JWT 검증은 환경변수 필요 | CI 환경 구성 후 |

---

## 환경 변수 (필수)

| 변수명 | 설명 |
|--------|------|
| `JWT_SECRET_KEY` | JWT 서명 키 (HS256) |
| `ENCRYPTION_KEY` | AES-256-GCM 마스터 키 (32바이트, base64) |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 클라이언트 시크릿 |
| `JWT_ALGORITHM` | 기본값 `HS256` |
| `JWT_EXPIRY_SECONDS` | 기본값 `3600` |

---

## 완료 체크리스트

- [x] domain 계층 전체 구현
- [x] application 계층 전체 구현
- [x] adapter 계층 전체 구현
- [x] unit/domain 테스트 전체 작성
- [x] unit/application 테스트 전체 작성
- [x] pytest 전체 통과 (26/26 PASS — 스펙 기준 재정렬 후)
- [x] Ruff lint 통과 (43건 수정, 2026-05-07, `All checks passed!`)
- [x] `modules/auth/report/auth_report.md` 작성
- [x] PR #19 → `development` 브랜치 (OPEN, 리뷰 반영 완료)
