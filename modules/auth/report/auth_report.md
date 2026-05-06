# auth (REQ-002) 결과 보고서

**모듈**: auth  
**REQ**: REQ-002  
**작성일**: 2026-05-06  
**담당자**: 박아름  
**브랜치**: `feature/req-002-auth`  
**상태**: ✅ PASS 완료

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
| adapters | 3 | `GoogleOAuthAdapter`, `JWTAdapter`, `AuthMiddleware` |

### 주요 구현 내용

- Google OAuth 2.0 코드 교환 → 세션 생성 → JWT 발급 전체 흐름 구현
- AES-256-GCM + Fernet 이중 cipher 구현 (`CipherPort` ABC 기반)
- `uuid.uuid5(NAMESPACE_DNS, google_sub)` 로 사용자 ID 결정론적 파생 (UserRepository 불필요)
- Refresh Token Rotation: 폐기된 세션으로 갱신 시도 시 E-AUTH-006 raise
- Pydantic v2 `frozen=True` 로 모든 도메인 엔티티/VO 불변성 보장
- FastAPI `BaseHTTPMiddleware` JWT 검증 미들웨어 (public path 화이트리스트 포함)
- `PermissionSource` 6차원 권한 모델: Admin(Restricted ceiling) / User(High ceiling) 분기

---

## 2. 테스트 결과

### 요약

| 구분 | 건수 |
|------|------|
| 전체 테스트 | 24건 |
| PASS | 24건 |
| FAIL | 0건 |
| SKIP | 0건 |

### 계층별 결과

| 계층 | 전체 | PASS | FAIL |
|------|------|------|------|
| unit/domain | 9 | 9 | 0 |
| unit/application | 15 | 15 | 0 |
| integration | 0 | - | - |

### 테스트 파일 목록

| 파일 | 테스트 케이스 |
|------|-------------|
| `unit/domain/test_session.py` | 유효/폐기/만료/불변성 |
| `unit/domain/test_permission_resolver.py` | Admin 권한, User 권한, VO 불변성 |
| `unit/domain/test_credential_injection.py` | 복호화 성공, 폐기된 연결 차단 |
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

해당 없음 (24/24 PASS)

---

## 6. 개선 내용 (실제 적용)

| 파일 | 변경 내용 | 이유 |
|------|-----------|------|
| `pyproject.toml` | `build-backend` → `setuptools.build_meta` | Python 3.14에서 `setuptools.backends.legacy` 미지원 |

---

## 7. 다음 단계 권고사항

- **REQ-003 (nodes-graph) 완성 후**: `CredentialInjectionService.inject()` 에 `node_id` 파라미터 추가 및 `NodeDefinitionRepository`로 risk_level/required_connections 검증 로직 보강 필요
- **REQ-008 (storage) 연동 시**: `SessionRepository`, `OAuthConnectionRepository` ABC 구현체 주입 확인 — Port 메서드 시그니처 계약(ADR-0005) 준수 여부 검증 필요
- **integration 테스트**: `AESGCMCipher`, `JWTAdapter` 실제 암복호화/서명 검증은 환경변수(`ENCRYPTION_KEY`, `JWT_SECRET_KEY`) 세팅 후 별도 작성 권장
