# ADR-0027: OAuth Connection authorize/저장 플로우 (생성 측)

- **Status**: Proposed (박아름 제안자 — 2026-06-08 e2e 검증 중 발견)
- **관련 이슈**: e2e 시나리오 `S-AREUM-2`(구글시트 읽기) staging 실행 시 `google_sheets_read` **401 (OAuth 토큰 없음)**
- **관련 PR**: #348 (OAuthConnectionResolver — 주입 측, 기 구현)

---

## Context

e2e 사용자 시나리오를 staging에서 실제 실행(execute)하니 `google_sheets_read`가 **401 "Expected OAuth 2 access token"**으로 실패. 진단 결과 OAuth connection이 **주입 측만 구현되고 생성 측이 없음**:

- ✅ **주입(consume) 측 (PR #348)**: `oauth_connections`에 connection이 *있으면* → `OAuthConnectionResolver`가 credential로 해소 → 노드에 토큰 선바인딩. 파이프라인 완비.
- ❌ **생성(authorize) 측**: 사용자가 google/slack을 authorize해서 토큰을 `oauth_connections`에 **저장하는 입구가 없음**. → 테이블이 비어 있어 resolver가 빈손 → 401.
- ⚠️ 프론트 `settings/page.tsx:168-170`은 가원 계정 하드코딩(`connected=true` 고정)이라 "연결됨" **거짓 표시**.

> 로그인용 google OAuth(`/auth/authorize`, openid/email scope)는 별개로 존재. 본 ADR은 **워크플로우 노드용 서비스 연동 토큰**(Sheets/Drive/Docs/Calendar/Slack scope) 생성 흐름이다.

---

## ✅ 이미 있는 것 (재사용 — 변경 없음)

| 구성 | 위치 |
|---|---|
| `oauth_connections` 테이블 (service, credential_id FK, access/refresh_token_encrypted, scopes, is_active…) | `database/schemas/008_oauth_security.sql` |
| `OAuthConnection` 엔티티 | `modules/auth/domain/entities/oauth_connection.py` |
| `OAuthConnectionRepository`: **`create` / `get_active_for_user` / `update_tokens` / `revoke` / `get_by_credential_id`** | `modules/auth/domain/ports/` |
| `CipherPort` / `AESGCMCipher` (토큰 암호화) | `modules/auth/` |
| `OAuthConnectionResolver` (노드 주입, PR #348) | `modules/ai_agent/adapters/connection_resolver_adapter.py` |

→ 저장·조회·갱신·해제·암호화·주입이 전부 구현됨. **남은 건 이들을 묶는 use case + 엔드포인트 + OAuth 토큰 교환뿐.**

---

## Decision — 생성 측 gap만 채운다

### use case (auth/application/use_cases)

1. `StartConnectionAuthorizeUseCase` — service별 `authorization_url` + `state`(CSRF, Redis) 생성
2. `CompleteConnectionUseCase` — callback `code` → 토큰 교환 → `repo.create(user_id, service, tokens)` (토큰은 `AESGCMCipher` 암호화)
3. `ListConnectionsUseCase` — `repo.get_active_for_user` 기반 사용자 연결 목록
4. `RevokeConnectionUseCase` — `repo.revoke`

### 엔드포인트 (api_server, `/api/v1/connections`)

| 메서드 | 경로 | 동작 |
|---|---|---|
| `GET` | `/connections` | 연결 목록 (settings 화면용 — service/account/connected) |
| `GET` | `/connections/{service}/authorize` | `authorization_url` 반환 → 프론트가 리다이렉트 |
| `GET` | `/connections/{service}/callback` | `code`→토큰교환→저장→프론트 settings로 복귀 |
| `DELETE` | `/connections/{service}` | 연결 해제 |

### scope (노드 `required_connections` 충족)

```
google: spreadsheets, drive, documents, calendar.events, gmail.send
        → google_sheets_read / google_docs_write / google_drive_read / google_calendar_create_event / gmail_send 전부 커버
slack:  chat:write, channels:read
```

### authorize 흐름

```
settings "Google 연결" 클릭
 → GET /connections/google/authorize → authorization_url (state 발급, Redis 저장)
 → 브라우저 google 동의화면 → 사용자 승인
 → GET /connections/google/callback?code=&state=
     → state 검증(CSRF, Redis GETDEL) → code로 access/refresh_token 교환
     → AESGCMCipher 암호화 → repo.create(user_id, "google", tokens)
     → 프론트 settings 리다이렉트 (연결됨)
 → 이후 execute 시 OAuthConnectionResolver가 자동 주입 → 401 해소
```

---

## 영역 분담

| 작업 | 담당 |
|---|---|
| use case 4 + 엔드포인트 4 + 토큰 교환 로직 | **박아름 (auth / api_server, REQ-002)** |
| google OAuth 앱 scope 추가 + staging redirect URI / slack 앱 생성·secret 등록 | **조장 (인프라)** |
| `settings/page.tsx` 하드코딩 제거 + `GET /connections` 연동 + "연결" 버튼 | **가원/조장 (프론트, REQ-010)** |

**순서**: ① 박아름 엔드포인트 스펙 확정 → ②(프론트 연동)·③(OAuth 앱 scope) 병행.

---

## Consequences

### Positive
- e2e 시나리오(google/slack 노드) staging 실제 실행 가능 → 조장 "실제 실행 검증" 충족.
- 주입 인프라(PR #348) 재사용 → 신규 작업이 use case 4 + 엔드포인트 4로 작음.
- 토큰 `AESGCMCipher` 암호화 저장 (평문 금지).

### Negative / Trade-offs
- google OAuth 앱 scope 확장 = Google 검증(verification) 필요 가능성 (민감 scope).
- 프론트 settings 더미 제거까지 묶여야 사용자 눈에 "연결됨"이 진실이 됨.

### 미해결 (논의 필요)
- **토큰 refresh 전략** — `update_tokens` 존재. 만료 시 트리거 주체 = resolver 만료 체크 후 갱신 vs 별도 스케줄.
- google 앱 scope를 **로그인 앱과 통합 vs 분리**(incremental authorization).
- `credentials` 테이블 ↔ `oauth_connections.credential_id` FK 저장 흐름 (connection 저장 시 credential row 동시 생성 여부).

---

## Alternatives Considered
- **프론트 더미 유지 + 백엔드만**: 거짓 "연결됨" 표시 잔존 → 사용자 혼란. 기각.
- **노드에 토큰 수동 입력**: 보안·UX 최악. 기각.
