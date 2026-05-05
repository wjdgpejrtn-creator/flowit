# api-server

> REQ-009: FastAPI 기반 HTTP 게이트웨이, SSE 스트리밍, DI 조립

## 설치

```bash
pip install -e services/api-server
pip install -e "services/api-server[dev]"
```

## 실행

```bash
uvicorn app.main:create_app --factory --reload --port 8000
```

## Quick Start (의존성 주입 예시)

```python
# services/api-server/app/dependencies/ 에서 모듈 조립
from ai_agent.application.use_cases import ComposeWorkflowUseCase
from auth.application.use_cases import AuthenticateUseCase
from storage.repositories import WorkflowRepository, AgentMemoryRepository

# FastAPI Depends()로 주입
async def get_compose_use_case() -> ComposeWorkflowUseCase:
    return ComposeWorkflowUseCase(
        memory_repo=AgentMemoryRepository(session=db_session),
        ...
    )
```

## 라우터 카탈로그

| 라우터 | 주요 엔드포인트 | 위임처 |
|--------|---------------|--------|
| workflows | POST/GET/PUT/DELETE `/api/v1/workflows[/{id}]`, `/execute` | REQ-008 WorkflowService |
| executions | GET `/api/v1/executions/{id}` | REQ-001 ExecutionRepository |
| agents | POST `/agents/register`, WS `/agents/ws`, heartbeat | 자체 (FR-009-05) |
| webhooks | POST `/webhooks/{workflow_id}/{path}` (HMAC) | 자체 (FR-009-06) |
| credentials | POST/GET/DELETE `/api/v1/credentials` | REQ-002 + REQ-001 |
| oauth | GET `/oauth/{provider}/start`, `/callback` | REQ-002 |
| connections | GET `/api/v1/connections` | REQ-002 |
| auth | GET `/api/v1/auth/session`, `/users/me`, `/departments` | REQ-002 |
| ai_composer | POST `/api/v1/ai/compose?stream=true`, `/rewind` | REQ-004 LangGraph |
| skills | POST `/skills/bootstrap`, `/answer`, `/{id}/approve`, `/reject`, GET `/skills`, `/marketplace` | REQ-004 + REQ-008 |
| nodes_catalog | GET `/api/v1/nodes/catalog`, POST `/reembed` (admin) | REQ-003 + REQ-001 |
| uploads | POST `/api/v1/uploads` | 자체 + GCS |
| parsed_documents | GET `/api/v1/parsed-documents/{id}` | REQ-006 |
| validate | POST `/api/v1/workflows/validate` | REQ-004 SchemaValidation |
| csrf | GET `/api/v1/auth/csrf-token` | REQ-002 |
| exec_control | POST `/api/v1/executions/{id}/cancel`, `/resume` | REQ-007 |
| health | GET `/health` | 자체 |

## 레이어 구조

```
app/
├── main.py              ← FastAPI 앱 팩토리
├── routers/             ← 엔드포인트 정의 (Inbound Adapter)
├── middleware/          ← 인증, CORS, 에러 핸들링, 로깅
├── dependencies/        ← DI 컨테이너 (Composition Root)
└── sse/                 ← SSE 스트리밍 핸들러
```

```
요청 흐름:
  HTTP Request
    → middleware/ (인증 검증, PermissionSource 주입)
    → routers/ (요청 파싱, DTO 변환)
    → modules/*/application/use_cases/ (비즈니스 로직)
    → modules/storage/repositories/ (영속화)
    → SSE/JSON Response
```

## 의존 관계

```
이 서비스 → auth (AuthMiddleware, AuthenticateUseCase)
이 서비스 → ai-agent (ComposeWorkflowUseCase)
이 서비스 → doc-parser (ParseDocumentUseCase)
이 서비스 → nodes-graph (ValidateGraphUseCase)
이 서비스 → toolset (RegisterToolUseCase)
이 서비스 → storage (모든 Repository 구현체)
이 서비스 → common-schemas (모든 DTO/응답 모델)
이 서비스 ← frontend (HTTP 클라이언트)
이 서비스 → execution-engine (Celery task dispatch)
```

## SSE 프레임 일람 (FR-009-09)

| 프레임 | 페이로드 | 생성 주체 |
|--------|---------|----------|
| `session` | chat_session_id, langgraph_thread_id | 본 모듈 |
| `agent_node` | 현재 실행 AgentNode 명 (consultant / intent / retriever / drafter / validator / security) | REQ-004 |
| `rationale_delta` | 사고 과정 실시간 델타 | REQ-004 |
| `slot_fill_question` | Slot Filling 재질문 | REQ-004 |
| `draft_spec_delta` | draft_spec 증분 | REQ-004 |
| `result` | intent ∈ {clarify, draft, refine, propose} | REQ-004 |
| `error` | 차단 / 실패 메시지 | 본 모듈 또는 REQ-004 |

## Permission Source Key (FR-009-16)

`request.state.permission_source` 필드:

| 필드 | 설명 |
|------|------|
| `user_id`, `role`, `department_id` | JWT payload 복사 (REQ-002) |
| `session_id` | chat / workflow / direct |
| `current_workflow_id` / `current_skill_id` | 의존성 있을 때 |
| `granted_scopes` | 현재 허용 범위 (Private / Team / Public) |
| `risk_ceiling` | 이 호출이 시도 가능한 최대 risk_level (User: High / Admin: Restricted) |

- 도구 (REQ-005) 는 본 permission_source에서만 권한을 읽음. 자체 JWT 디코딩 / DB 조회 금지
- permission_source 우회 시도는 security_logs `event_type=PERMISSION_SOURCE_TAMPERING` 기록

## 표준 에러 스키마

```json
{
  "validation_status": "failed",
  "errors": [
    {
      "code": "E_NODE_TYPE_MISMATCH",
      "message": "노드 A 출력 'table' 이 노드 B 입력 'text' 와 불일치",
      "node_ids": ["node_a", "node_b"],
      "edge_id": "edge_ab",
      "validator": "SchemaValidation",
      "hint": "노드 B 앞에 JSON→Text 변환 노드 추가"
    }
  ]
}
```

## 실행 모드 디스패치 (FR-009-04)

| execution_mode | 대상 | 전송 방식 |
|---------------|------|----------|
| `serverless` | Execution_Engine Celery Worker | 태스크 큐잉 (Redis broker) |
| `agent` | 고객 VPC Agent | WebSocket push (RSA 재암호화 자격증명) |

## 파일 업로드 (FR-009-15)

| 항목 | 값 |
|------|---|
| 엔드포인트 | `POST /api/v1/uploads` |
| 요청 | multipart/form-data, file + workflow_id (선택) + intended_use + purpose (선택) |
| 운영 저장 경로 | `gs://bucket/storage/input/{workflow_id}/{uuid}_{filename}` |
| 최대 파일 크기 | 10MB |
| 임시 업로드 TTL | 24시간 (workflow_id 미지정 시) |

## doc_parser 호출 방식 (FR-009-14)

| 시나리오 | 방식 |
|---------|------|
| 일반 문서 (10MB 이하 / 60초 이하) | 동일 프로세스 모듈 직접 import |
| 대용량 / 비동기 | Celery 큐잉 + 202 Accepted + parsed_document_id 폴링 (Phase 2) |

- doc_parser는 자체 REST 노출 X (보안 레이어 우회 방지). 모든 입구는 본 모듈 경유

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `API_HOST` | N | 바인딩 호스트 (기본: 0.0.0.0) |
| `API_PORT` | N | 바인딩 포트 (기본: 8000) |
| `CORS_ORIGINS` | Y | 허용 오리진 목록 (쉼표 구분) |
| `REDIS_URL` | Y | Redis 연결 URL (세션 캐시 + Celery broker) |
| `DB_HOST` | Y | PostgreSQL 호스트 |
| `DB_PORT` | N | PostgreSQL 포트 (기본: 5432) |
| `DB_USER` | Y | DB 사용자명 |
| `DB_PASSWORD` | Y | DB 비밀번호 |
| `DB_NAME` | Y | DB 이름 |

## 아키텍처 제약 (옵션 A)

- 비즈니스 로직 직접 구현 금지 — 항상 위임처 호출
- credential 평문은 라우터 코드에서 절대 다루지 않음
- doc_parser 자체 REST 노출 금지, 본 모듈 경유만

## 비기능 제약

| 항목 | 기준 |
|------|------|
| 일반 라우터 P95 | < 200ms |
| SSE 첫 프레임 도달 (TTFB) | < 1초 |
| 파일 업로드 10MB | < 5초 (us-central1) |
| credential 평문 노출 | 0건 (라우터 / 로그 / 응답) |
| 관측성 | 모든 응답에 X-Request-Id 헤더 |

## 테스트

```bash
pytest services/api-server/tests/
```
