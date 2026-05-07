# api-server

> REQ-009: FastAPI 기반 HTTP 게이트웨이, SSE 스트리밍, Composition Root
>
> 구현 명세 → [`docs/specs/REQ-009-api-server.md`](../../docs/specs/REQ-009-api-server.md)

## 설치

```bash
pip install -e services/api-server
pip install -e "services/api-server[dev]"
```

## 실행

```bash
uvicorn src.main:create_app --factory --reload --port 8000
```

## 아키텍처 역할

API 서버는 **Composition Root** — 비즈니스 로직을 직접 구현하지 않고, 모든 유스케이스를 Port 인터페이스를 통해 호출합니다. 구체 구현체는 `DependencyContainer`에서 주입합니다.

## 라우터 카탈로그

| 라우터 | 주요 엔드포인트 | 위임처 |
|--------|---------------|--------|
| `workflows` | `POST/GET/PUT/DELETE /workflows[/{id}]` | REQ-008 Storage |
| | `POST /workflows/{id}/validate` | REQ-003 GraphValidator |
| | `POST /workflows/{id}/execute` | REQ-007 Celery dispatch |
| `agents` | `POST /agents/sessions` | REQ-004 ComposeWorkflowUseCase |
| | `GET /agents/sessions/{id}/stream` | SSE 스트리밍 (AnySSEFrame) |
| | `POST /agents/sessions/{id}/messages` | REQ-004 ContinueConversationUseCase |
| `documents` | `POST /documents/upload` | REQ-008 Storage + GCS |
| | `GET /documents/{id}` | REQ-006 ParseDocumentUseCase |
| | `POST /documents/{id}/analyze` | REQ-004 문서 분석 |
| `auth` | `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me` | REQ-002 AuthenticateUseCase |
| `nodes` | `GET /nodes/catalog` | REQ-003 NodeDefinitionRepository |
| `skills` | `POST /skills/bootstrap`, `GET /skills`, `GET /marketplace` | REQ-004 + REQ-008 |
| `exec_control` | `POST /executions/{id}/cancel`, `/resume` | REQ-007 PauseResumeUseCase |
| `health` | `GET /health` | 자체 |

## domain — TopologicalScheduler

```python
class TopologicalScheduler:
    def schedule(self, nodes: list[NodeInstance], edges: list[Edge]) -> list[list[UUID]]:
        """Kahn's algorithm 위상 정렬. 실행 레벨별 instance_id 그룹 반환."""
        ...

    def validate_dag(self, nodes: list[NodeInstance], edges: list[Edge]) -> ValidationErrorResponse:
        """DAG 유효성 검증 (순환, 고립 노드, 중복 ID 등)."""
        ...
```

## SSE 스트리밍 프레임

| 프레임 | 페이로드 | 생성 주체 |
|--------|---------|----------|
| `SessionFrame` | session_id, langgraph_thread_id | 본 모듈 |
| `AgentNodeFrame` | 현재 실행 AgentNode 명 | REQ-004 |
| `RationaleDeltaFrame` | 사고 과정 실시간 델타 | REQ-004 |
| `SlotFillQuestionFrame` | Slot Filling 재질문 | REQ-004 |
| `DraftSpecDeltaFrame` | draft_spec 증분 | REQ-004 |
| `ResultFrame` | intent (clarify/draft/refine/propose) | REQ-004 |
| `ErrorFrame` | 차단/실패 메시지 | 본 모듈 또는 REQ-004 |

> 모든 프레임은 `AnySSEFrame` discriminated union으로 `frame_type` 기반 역직렬화.

## Permission Source Key

`request.state.permission_source` — 모든 유스케이스 호출 시 전달:

| 필드 | 설명 |
|------|------|
| `user_id`, `role`, `department_id` | JWT payload (REQ-002) |
| `session_id` | chat / workflow / direct |
| `granted_scopes` | 허용 범위 (Private / Team / Public) |
| `risk_ceiling` | 시도 가능한 최대 risk_level (User: High / Admin: Restricted) |

## 의존 관계

```
Upstream (이 서비스가 의존 — Use Case 호출):
  ├── auth (REQ-002)           → AuthenticateUseCase, PermissionResolver
  ├── ai-agent (REQ-004)       → ComposeWorkflowUseCase, ContinueConversationUseCase
  ├── doc-parser (REQ-006)     → ParseDocumentUseCase, ParsingPipeline
  ├── nodes-graph (REQ-003)    → ValidateGraphUseCase, SearchNodesUseCase
  ├── toolset (REQ-005)        → ListToolsUseCase
  ├── storage (REQ-008)        → 모든 Repository 구현체 (DI 주입)
  ├── common-schemas (REQ-012) → 모든 DTO/응답 모델
  └── execution-engine (REQ-007) → Celery task dispatch

Downstream (이 서비스를 소비):
  └── frontend (REQ-010)       → HTTP REST + SSE 클라이언트
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `API_HOST` | N | 바인딩 호스트 (기본: 0.0.0.0) |
| `API_PORT` | N | 바인딩 포트 (기본: 8000) |
| `CORS_ORIGINS` | Y | 허용 오리진 목록 (쉼표 구분) |
| `REDIS_URL` | Y | Redis (세션 캐시 + Celery broker) |
| `DB_HOST` | Y | PostgreSQL 호스트 |
| `DB_PORT` | N | PostgreSQL 포트 (기본: 5432) |
| `DB_USER` | Y | DB 사용자명 |
| `DB_PASSWORD` | Y | DB 비밀번호 |
| `DB_NAME` | Y | DB 이름 |

## 아키텍처 제약

- 비즈니스 로직 직접 구현 금지 — 항상 위임처 호출
- credential 평문은 라우터 코드에서 절대 다루지 않음
- doc_parser 자체 REST 노출 금지 — 본 모듈 경유만

## 비기능 제약

| 항목 | 기준 |
|------|------|
| 일반 라우터 P95 | < 200ms |
| SSE 첫 프레임 도달 (TTFB) | < 1초 |
| 파일 업로드 10MB | < 5초 |
| credential 평문 노출 | 0건 |
| 관측성 | 모든 응답에 X-Request-Id 헤더 |

## 테스트

```bash
pytest services/api-server/tests/
```
