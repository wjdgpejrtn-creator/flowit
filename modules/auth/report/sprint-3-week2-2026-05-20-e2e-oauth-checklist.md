# Sprint 3 Week 2 — 2026-05-20 (수) 박아름 e2e OAuth→노드→로그인 통합 시나리오 검증 체크리스트

## 목적

OAuth 미연동 사용자가 외부 연결 필요 노드(slack/google)를 워크플로우에 넣었을 때, **검증 에러 → 로그인 페이지 유도**까지 이어지는 e2e 통합 흐름을 staging 배포 후 검증하기 위한 체크리스트.

박아름 영역(auth + nodes_graph) 단위 테스트는 완료됐으나, **전체 통합 흐름은 staging api_server 배포 후에야 검증 가능** (현재 미검증). 본 문서는 staging 배포 시 바로 검증할 수 있게 시나리오를 정리한 것.

## 전제 조건

- [ ] staging api_server 배포 완료 (조장 REQ-009, terraform apply + Cloud Run deploy)
- [ ] staging frontend 배포 완료 (조장 REQ-010)
- [ ] staging execution_engine worker 배포 완료 (조장 REQ-007, PR #90)
- [ ] staging DB seeds — node_definitions 53종 적용 (slack/google required_connections 노드 포함)
- [ ] Google OAuth client_id staging 등록 (redirect_uri staging 도메인)

## e2e 통합 시나리오 흐름

```
① OAuth 로그인 (Google)
   POST /auth/login 또는 /auth/callback → JWT 발급
        ↓
② 인증 컨텍스트 확인
   GET /auth/me → PermissionSource (JIT user auto-provisioning, PR #88)
        ↓
③ 워크플로우 생성 (slack/google 노드 포함)
   AI Composer 또는 수동 — required_connections=["slack"] 노드 포함
        ↓
④ 워크플로우 검증
   POST /workflows/{id}/validate → ValidateGraphUseCase → GraphValidator
   - 노드 required_connections 있는데 credential_id None
   → ValidationError "Node requires external connection: [...]"
        ↓
⑤ (연동 시도) OAuth 연결
   사용자가 slack/google 연동 → oauth_connections INSERT
        ↓
⑥ 노드 실행 + credential 주입
   execution_engine dispatch_node → (toolset 노드) ExecuteToolUseCase
   → CredentialInjectionService.inject → conn 활성 → 복호화 → PlaintextCredential
        ↓
⑦ (미연동 시) 로그인 페이지
   frontend LoginPage (app/login/page.tsx) — OAuth2 로그인 유도
```

## 검증 체크리스트 (단계별)

### A. 인증 흐름 (박아름 auth 영역)

- [ ] `POST /auth/login` (또는 `/auth/callback`) — Google OAuth code 교환 → JWT 발급 (`authenticate_use_case.py`)
- [ ] JIT auto-provisioning — 첫 로그인 시 `users` 테이블 INSERT (PR #88, `find_by_id` None → `create`)
- [ ] `GET /auth/me` — JWT 디코드 → PermissionSource 반환 (NotFoundError 없음 확인)
- [ ] 재로그인 — 기존 user 유지 (`created_at` 변경 없음)

### B. 워크플로우 검증 — 미연동 감지 (박아름 nodes_graph 영역)

- [ ] slack 노드(required_connections=["slack"]) 포함 워크플로우 생성
- [ ] credential 미연동 상태로 `POST /workflows/{id}/validate` 호출
- [ ] **기대**: `GraphValidator._check_required_connections` → ValidationError "Node requires external connection: ['slack']"
- [ ] ValidationError 응답이 api_server `ValidationErrorResponse`로 전달되는지

### C. 자격증명 주입 — 미연동 시 에러 (박아름 auth 영역)

- [ ] 미연동 상태로 노드 실행 시도 (execution_engine)
- [ ] **기대**: `CredentialInjectionService.inject` → conn None → NotFoundError "Credential not found or inactive"
- [ ] RESTRICTED 등급 노드 → AuthorizationError 확인
- [ ] toolset 노드 경로 — `ExecuteToolUseCase` → `CredentialInjectionService` 호출 확인

### D. 로그인 페이지 유도 — 통합 (조장 frontend/api_server 영역, 박아름 협업)

- [ ] 검증 에러/주입 에러 → frontend가 로그인 페이지로 리다이렉트하는지
- [ ] `LoginPage` (`services/frontend/app/login/page.tsx`) OAuth2 로그인 렌더
- [ ] 로그인 후 원래 워크플로우로 복귀하는지 (redirect_uri 처리)

### E. 연동 후 정상 흐름

- [ ] slack/google 연동 완료 → `oauth_connections` INSERT
- [ ] 재검증 — ValidationError 사라짐
- [ ] 노드 실행 → credential 주입 성공 → 워크플로우 정상 실행

## 영역별 책임 매핑

| 단계 | 책임 영역 | 담당 | 단위 검증 |
|------|----------|------|----------|
| A. OAuth 로그인 + JIT | auth `AuthenticateUseCase` | 박아름 | ✅ unit (test_authenticate 34) |
| B. 워크플로우 검증 (required_connections) | nodes_graph `GraphValidator` | 박아름 | ✅ unit (test_graph_validator) |
| C. credential 주입 | auth `CredentialInjectionService` | 박아름 | ✅ unit (test_credential_injection) |
| (연결) api_server validate/auth router | api_server | 조장 REQ-009 | api_server unit |
| (연결) execution_engine credential 경로 | execution_engine | 조장 REQ-007 | execution_engine unit |
| D. 로그인 페이지 + 리다이렉트 | frontend `LoginPage` | 조장 REQ-010 | ⚠️ 미검증 |

## 알려진 불명확 지점 (검증 시 확인 필요)

1. **execution_engine credential 경로 두 갈래**: toolset 노드 = auth `CredentialInjectionService` / 그 외 = 자체 `vault_credential_provider`. 어떤 노드가 어느 경로인지 staging에서 확인.
2. **검증 에러 → 로그인 페이지 트리거**: api_server가 ValidationError를 어떤 형식으로 frontend에 전달하고, frontend가 어떻게 로그인 페이지로 유도하는지 (현재 통합 흐름 미정의).
3. **redirect_uri 복귀**: 로그인 후 원래 작업 컨텍스트로 돌아가는 흐름 (frontend 라우팅).

## 실패 시 디버깅 포인트

| 증상 | 확인 위치 |
|------|----------|
| `/auth/me` NotFoundError | JIT auto-provisioning 동작 확인 (`authenticate_use_case.py` JIT 블록 + PR #75 DI 주입) |
| 검증 에러 안 뜸 | `GraphValidator._check_required_connections` + node `credential_id` 상태 |
| credential 주입 실패 | `oauth_connections` 테이블 상태 + `CredentialInjectionService` conn 조회 |
| 로그인 페이지 안 뜸 | frontend 에러 핸들링 + api_server 에러 응답 형식 (조장 영역) |

## 박아름 검증 진행 시점

staging api_server 배포 완료 후 ([[project_staging_api_server_verification]] 트리거). A/B/C(박아름 영역)는 박아름이 직접 검증, D(frontend 통합)는 조장 협업.

## 관련 문서

- spec: `docs/specs/REQ-002-auth.md` §AuthenticateUseCase, §CredentialInjectionService
- nodes_graph: `modules/nodes_graph/domain/services/graph_validator.py:126` `_check_required_connections`
- auth: `modules/auth/domain/services/credential_injection_service.py`
- frontend: `services/frontend/README.md` L91 `LoginPage`
