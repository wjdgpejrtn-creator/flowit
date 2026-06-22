# ADR-0021: 프론트엔드 인증 — OAuth backend-callback + 단일 출처 토폴로지

- **Status**: Accepted (2026-05-22 조장 협의 — 인프라 PR #140 머지로 토폴로지 확정)
- **Date**: 2026-05-22
- **Deciders**: @dhwang0803-glitch (조장, REQ-009/010/011)
- **Tags**: area/frontend, area/api_server, area/infra, auth, topology

## Context

REQ-010 frontend를 api_server와 연동하고 Google SSO 로그인을 붙이는 과정에서, 햄햄(이가원, REQ-010)이 "`GOOGLE_REDIRECT_URI`를 프론트 `/auth/callback` 경로에 맞춰달라"는 요청을 보냈다. 코드 검증 결과 두 가지 결정이 필요했다.

2026-05-22 코드 검증으로 확인한 사실:

- (a) api_server에 **자체 OAuth 콜백 `GET /api/v1/auth/callback`이 이미 존재** — `_consume_oauth_state`로 Redis `state` CSRF 검증 포함. 즉 backend가 콜백을 받도록 설계돼 있다.
- (b) `POST /api/v1/auth/login`(code를 body로 받는 경로)은 **`state`를 검증하지 않는다** — 프론트가 콜백을 받아 code를 전달하는 방식(B안)으로 가면 OAuth CSRF 보호가 빠진다.
- (c) Cloud Run은 서비스마다 별도 `*.run.app` 도메인을 부여한다 — frontend와 api_server를 그대로 두면 cross-origin이라 SSO 쿠키 공유가 불가능하다.
- (d) frontend `middleware.ts`는 `access_token` **쿠키**를 전제하나, frontend README는 "JWT는 메모리만"이라고 적혀 있어 내부 모순.
- (e) 시스템은 **단일 인스턴스**다 (ADR-0020 (e) 재확인) — "단일 도메인"은 회사별(멀티테넌트) 분리가 아니라 frontend/api_server 분리를 뜻한다.

결정 1 — OAuth 콜백 수신 주체: backend(A) vs frontend(B).
결정 2 — frontend ↔ api_server 토폴로지: SSO 쿠키가 same-origin이 되도록.

## Decision

### 1. OAuth A안 — backend가 콜백을 수신

`GOOGLE_REDIRECT_URI` = `{단일 도메인}/api/v1/auth/callback`. Google이 브라우저를 api_server 콜백으로 리다이렉트 → backend가 code 교환 → HttpOnly 쿠키 set → frontend 루트(`/`)로 302.

근거: code 교환과 client secret이 브라우저를 거치지 않아 더 안전하고, `GET /callback`의 Redis `state` CSRF 검증을 그대로 유지한다. B안은 `POST /login`이 `state`를 검증하지 않아 CSRF 보호가 빠진다 (사실 (b)).

### 2. 단일 출처 토폴로지

frontend가 public 진입점이고, `next.config` rewrites가 `/api/*` 를 api_server로 프록시한다. 브라우저는 frontend 도메인 하나만 보므로 SSO 쿠키가 same-origin으로 동작 — CORS·크로스도메인 쿠키 설정이 불필요하다.

Cloud Run 구현: frontend(public) + api_server(public), frontend의 `next.config` rewrites가 `/api`를 프록시. HTTP(S) Load Balancer + URL map은 채택하지 않는다 — 6주 staging 데모 규모(프로젝트 종료 2026-06-30)에 LB 비용·terraform 복잡도가 과하다.

### 3. HttpOnly 쿠키 인증

`access_token`/`refresh_token`을 `HttpOnly; Secure; SameSite=Lax` 쿠키로 backend가 set한다. api_server `get_permission_source`는 `Authorization` 헤더 대신 쿠키에서 JWT를 읽는다. frontend는 JS로 토큰을 다루지 않는다 (JS가 못 읽음 = XSS 내성). frontend README의 "JWT 메모리만" 문구는 본 쿠키 방식으로 정정한다 (사실 (d) 모순 해소).

### 4. 단일 인스턴스 전제 재확인

"단일 도메인"은 frontend/api_server 분리를 뜻하며 회사별 멀티테넌트 분리가 아니다. 시스템은 단일 인스턴스다 (ADR-0020 (e)). 멀티테넌시가 필요해지면 별도 ADR로 다룬다.

## Consequences

### 외부 모듈 영향

- **api_server** (REQ-009) — `GET /callback`을 JSON 반환에서 **쿠키 set + frontend로 302**로 변경. `get_permission_source`가 `access_token` 쿠키를 읽도록 변경. `POST /refresh`도 쿠키 기반. 로그아웃 엔드포인트(쿠키 clear) 신설. `FRONTEND_URL` env 추가.
- **frontend** (REQ-010) — `next.config.mjs` 신설(`/api/*` rewrite, destination `process.env.API_PROXY_TARGET`). 로그인 버튼 → `GET /api/v1/auth/authorize` 호출 후 `authorization_url` 이동. `middleware.ts` 쿠키 검사 활성화. `/auth/callback` 라우트 미생성(A안이라 불필요). README 쿠키 방식 정정.
- **infra** (REQ-011) — frontend Cloud Run 서비스 신설(PR #140 머지 — `google_service_account.frontend` 최소권한 SA). `GOOGLE_REDIRECT_URI` secret 갱신. Google Cloud Console에 redirect URI 등록. 순환 의존 회피용 2단계 apply.

### 긍정

- CORS·크로스도메인 쿠키 이슈를 토폴로지 차원에서 제거.
- code 교환·client secret이 브라우저 미경유 — B안보다 안전.
- `GET /callback`의 `state` CSRF 검증 유지.
- HttpOnly 쿠키 — JS가 토큰에 접근 불가, XSS 내성.

### 부정 / 제약

- frontend가 `/api` 요청을 프록시하는 hop 1개 추가.
- frontend·api_server URL이 서로 물려 2단계 apply 필요 (PR #140이 `var.frontend_url`로 순환 회피).
- 로컬 개발은 포트가 달라(`:3000`/`:8000`) `next.config` rewrites로 same-origin을 흉내내야 한다.

## Alternatives Considered

### B안 — frontend가 콜백 수신 후 `POST /login`에 code 전달 (기각)
`POST /login`이 `state`를 검증하지 않아 OAuth CSRF 보호가 빠진다 (사실 (b)). code가 브라우저를 경유한다. A안 대비 보안 약점.

### 서브도메인 분리 (`app.` / `api.`) (기각)
cross-origin이라 CORS + `Domain=.<도메인>` 쿠키 설정이 필요하다. 단일 출처(path 라우팅) 대비 복잡도만 늘고 데모 규모에 이점이 없다.

### HTTP(S) Load Balancer + URL map (기각)
`/`→frontend, `/api`→api_server를 LB가 분기하면 토폴로지는 깔끔하나, 6주 staging 데모에 LB 비용·terraform 복잡도가 과하다.

## Related ADRs

- **ADR-0005** — SessionRepository / OAuthConnectionRepository 계약 (OAuth 흐름 기반).
- **ADR-0020** — (e) 단일 인스턴스 전제를 본 ADR이 재확인.

## References

- 설계 논의: 2026-05-22 조장 ↔ 이가원 (REQ-010 연동 요청 발단)
- 인프라 구현: PR #140 (frontend Cloud Run + 단일 출처 토폴로지 terraform)
