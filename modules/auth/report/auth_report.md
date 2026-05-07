# auth (REQ-002) 결과 보고서

**모듈**: auth  
**REQ**: REQ-002  
**작성일**: 2026-05-06 (최종 수정: 2026-05-07)  
**담당자**: 박아름  
**브랜치**: `feature/req-002-auth`  
**상태**: ✅ PASS 완료 (PR #19 리뷰 대기)

---

## 1. 개발 결과

### 대상 계층

| 계층 | 파일 수 | 주요 구현 |
|------|--------|----------|
| domain/entities | 2 | `Session`, `OAuthConnection` |
| domain/value_objects | 1 | `TokenPair` |
| domain/ports | 3 | `CipherPort`, `SessionRepository`, `OAuthConnectionRepository` |
| domain/services | 2 | `PermissionResolver`, `CredentialInjectionService` |
| application/use_cases | 4 | `AuthenticateUseCase`, `IssueTokenUseCase`, `RefreshTokenUseCase`, `InjectCredentialUseCase` |
| adapters/cipher | 3 | `BaseCipher`, `AESGCMCipher`, `FernetCipher` |
| adapters/oauth | 1 | `GoogleOAuthClient` (스펙 기준 신규) |
| adapters | 3 | `GoogleOAuthAdapter`, `JWTAdapter`, `AuthMiddleware` |

### 주요 구현 내용

- Google OAuth 2.0 코드 교환 → 세션 생성 → JWT 발급 전체 흐름 구현
- AES-256-GCM + Fernet 이중 cipher 구현 (`CipherPort` ABC 기반)
- `uuid.uuid5(NAMESPACE_DNS, google_sub)` 로 사용자 ID 결정론적 파생 (UserRepository 불필요)
- Refresh Token Rotation: 폐기된 세션으로 갱신 시도 시 E-AUTH-006 raise
- `TokenPair` VO만 `frozen=True` — `Session`, `OAuthConnection` 엔티티는 `revoke()` 메서드 지원을 위해 mutable (스펙 기준)
- `Session.is_expired()` / `Session.revoke()`, `OAuthConnection.revoke()` / `is_active` 필드 (스펙 기준 재정렬)
- `CredentialInjectionService.inject(credential_id, node_id)` — `NodeDefinitionRepository`로 risk_level/required_connections 검증 (H-4 완성)
- FastAPI `BaseHTTPMiddleware` JWT 검증 미들웨어 (public path 화이트리스트 포함)
- `PermissionSource` 6차원 권한 모델: Admin(Restricted ceiling) / User(High ceiling) 분기

---

## 2. 테스트 결과

### 요약

| 구분 | 건수 |
|------|------|
| 전체 테스트 | 26건 |
| PASS | 26건 |
| FAIL | 0건 |
| SKIP | 0건 |

### 계층별 결과

| 계층 | 전체 | PASS | FAIL |
|------|------|------|------|
| unit/domain | 11 | 11 | 0 |
| unit/application | 15 | 15 | 0 |
| integration | 0 | - | - |

### 테스트 파일 목록

| 파일 | 테스트 케이스 |
|------|-------------|
| `unit/domain/test_session.py` | is_expired/폐기/만료/device_info/revoke() |
| `unit/domain/test_permission_resolver.py` | Admin 권한, User 권한, VO 불변성 |
| `unit/domain/test_credential_injection.py` | inject(credential_id, node_id), NodeDef risk_level/service_type 검증, 폐기 연결 차단 |
| `unit/application/test_authenticate.py` | 토큰 발급, user_id 결정론적 파생, 암호화 저장, 재인증 토큰 갱신 |
| `unit/application/test_issue_token.py` | 토큰 발급, type 검증, 폐기/만료 세션 차단 |
| `unit/application/test_refresh_token.py` | 갱신 성공, access token으로 갱신 시도 차단, 무효 토큰, 폐기 세션 |
| `unit/application/test_inject_credential.py` | 복호화 성공, 폐기 연결 차단, 미존재 연결 차단 |

---

## 3. Review Findings

| 점검 축 | 발견 건수 | 최고 심각도 |
|---------|---------|-----------|
| Correctness | 0 | - |
| Error handling | 0 | - |
| Test coverage | 0 | - |
| Performance | 0 | - |
| API 설계 | 0 | - |
| Clean Architecture | 0 | - |
| Readability | 0 | - |

Critical/Major 없음.

---

## 4. Clean Architecture 준수 점검

- [x] 의존성 방향 위반 0건 (domain에 FastAPI/SQLAlchemy import 없음)
- [x] ORM 모델 도메인 누출 0건
- [x] 공유 타입 SSOT 준수 (`PermissionSource`, `PlaintextCredential` → `common_schemas`)
- [x] Port/Adapter 분리 유지 (`CipherPort` ABC → `auth/adapters/cipher/` 구현)

---

## 5. 오류 원인 분석

해당 없음 (26/26 PASS)

---

## 6. 개선 내용 (실제 적용)

| 파일 | 변경 내용 | 이유 |
|------|-----------|------|
| `pyproject.toml` | `build-backend` → `setuptools.build_meta` | Python 3.14에서 `setuptools.backends.legacy` 미지원 |
| `domain/entities/session.py` | `frozen=True` 제거, `is_expired()` / `revoke()` 추가, `device_info` 필드 추가 | docs/specs 기준 재정렬 (2026-05-07) |
| `domain/entities/oauth_connection.py` | 필드명 정규화(`access_token_encrypted` 등), `is_active` + `revoke()` | docs/specs 기준 재정렬 (2026-05-07) |
| `domain/ports/session_repository.py` | `create(**kwargs)` 패턴으로 확장 | docs/specs 기준 재정렬 (2026-05-07) |
| `domain/ports/oauth_repository.py` | `create/update_tokens(tokens: dict)` 패턴, 반환 타입 `Optional` | docs/specs 기준 재정렬 (2026-05-07) |
| `domain/services/credential_injection.py` | `inject(credential_id, node_id)` — `NodeDefinitionRepository` 교차 의존 추가 (H-4 완성) | docs/specs 기준 재정렬 (2026-05-07) |
| `application/use_cases/authenticate.py` | `tokens: dict` 패턴, `if existing is not None` 분기 | docs/specs 기준 재정렬 (2026-05-07) |
| `adapters/oauth/google_oauth_client.py` | `GoogleOAuthClient` 신규 추가 (스펙 명시 어댑터) | docs/specs 기준 재정렬 (2026-05-07) |
| 전체 unit tests | 스펙 기준 시그니처/필드명 전면 수정 | docs/specs 기준 재정렬 (2026-05-07) |

---

## 7. 다음 단계 권고사항

- ~~**REQ-003 연동**: `CredentialInjectionService.inject()` `node_id` 파라미터 추가~~ → ✅ 완료 (2026-05-07, PR #19)
- **REQ-008 (storage) 연동 시**: `SessionRepository`, `OAuthConnectionRepository` ABC 구현체 주입 확인 — `**kwargs` / `tokens: dict` 패턴 계약(ADR-0005) 준수 여부 검증 필요
- **integration 테스트**: `AESGCMCipher`, `JWTAdapter` 실제 암복호화/서명 검증은 환경변수(`ENCRYPTION_KEY`, `JWT_SECRET_KEY`) 세팅 후 별도 작성 권장
- **Ruff lint**: 스펙 기준 재정렬 후 미실행 — `feature/req-002-auth` 브랜치에서 확인 필요
