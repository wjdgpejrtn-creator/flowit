# REQ-009 API Server — 구현 명세

- **담당자**: 황대원
- **모듈 경로**: `services/api_server/`
- **기술 스택**: Python 3.12+ (ADR-0007), FastAPI, Uvicorn, SSE (Server-Sent Events)
- **아키텍처 계층**: Interface Adapters (Inbound — HTTP → Use Case)

---

## 1. common_schemas에서 import할 클래스

### 1.1 Python import (from common_schemas)

| 클래스/타입 | 소스 모듈 | 용도 |
|------------|-----------|------|
| `WorkflowSchema` | `workflow` | 워크플로우 CRUD 엔드포인트 요청/응답 직렬화 |
| `NodeInstance` | `workflow` | 워크플로우 내 노드 인스턴스 직렬화 (위상 정렬은 execution_engine 책임) |
| `NodeConfig` | `workflow` | 노드 카탈로그 조회 응답 (56종 — gemma_chat 포함, PR #68) |
| `Edge` | `workflow` | 워크플로우 그래프 연결 정보 |
| `Position` | `workflow` | 프론트엔드 캔버스 좌표 전달 |
| `AgentState` | `agent` | 에이전트 세션 상태 SSE 스트리밍 |
| `SSEFrame` | `transport` | SSE 프레임 베이스 클래스 |
| `SessionFrame` | `transport` | 세션 시작 시 session_id + langgraph_thread_id 전달 |
| `AgentNodeFrame` | `transport` | 현재 실행 중인 에이전트 노드 알림 |
| `RationaleDeltaFrame` | `transport` | 에이전트 추론 과정 실시간 스트리밍 |
| `SlotFillQuestionFrame` | `transport` | 슬롯 필링 질문 전달 |
| `DraftSpecDeltaFrame` | `transport` | 드래프트 스펙 증분 업데이트 |
| `ResultFrame` | `transport` | 최종 결과 전달 |
| `ErrorFrame` | `transport` | 에러 발생 시 SSE 에러 프레임 |
| `AnySSEFrame` | `transport` | Discriminated Union — frame_type 기반 역직렬화 |
| `ValidationErrorItem` | `validation` | 검증 에러 개별 항목 |
| `ValidationErrorResponse` | `validation` | 검증 에러 응답 전체 포맷 |
| `ExecutionStatus` | `enums` | 워크플로우 실행 상태 열거형 |
| `AgentMode` | `enums` | 에이전트 모드 열거형 (onboarding/wizard/edit/general/security/**skill_builder**) |
| `IntentType` | `enums` | 의도 분류 Enum 5값 — clarify/draft/refine/propose/build_skill (v0.4.0 PR #72). `ResultFrame.intent` 직렬화 |
| `AgentProtocolRequest` / `AgentProtocolResponse` | `agent_protocol` | OrchestratorClient 어댑터의 요청·응답 페이로드 (REQ-004 §4) |
| `MemoryEntry` | `agent` | sub-agent 페이로드 (Sprint 3에서 ai_agent → common_schemas 이관) |
| `WorkflowSchema.owner_user_id: Optional[UUID]` | `workflow` | v0.3.0 PR #66 — Repository.save 시점에 PermissionSource.user_id 명시 주입 필요 |

### 1.2 import 코드 예시

```python
from common_schemas import (
    WorkflowSchema, NodeInstance, NodeConfig, Edge, Position,
    AgentState,
    SSEFrame, SessionFrame, AgentNodeFrame, RationaleDeltaFrame,
    SlotFillQuestionFrame, DraftSpecDeltaFrame, ResultFrame, ErrorFrame,
    AnySSEFrame,
    ValidationErrorItem, ValidationErrorResponse,
    ExecutionStatus, AgentMode, IntentType,
    AgentProtocolRequest, AgentProtocolResponse,
    MemoryEntry,
)
```

---

## 2. 이 모듈에서 구현할 클래스/컴포넌트

### 2.1 Domain — 책임 분리 (PR #67 단일 소유 정책)

api_server는 별도 도메인 로직을 보유하지 않는다. 다음 표대로 다른 모듈/서비스에 위임한다.

| 작업 | 위임처 | 호출 시점 |
|------|--------|----------|
| 그래프 정적 검증 (cycle / isolated / dup-id) | `nodes_graph.domain.services.GraphValidator` | `POST /workflows/{id}/validate` 라우터 |
| 위상 정렬 + 레벨별 실행 그룹 계산 | `execution_engine.src.domain.services.TopologicalScheduler` | Celery worker (POST /workflows/{id}/execute dispatch 후) |
| Skill 검색·승급 | `skills_marketplace.application.use_cases.*` | `/skills`, `/marketplace` 라우터 |

> 이전 명세에 있던 `api_server` 자체의 `TopologicalScheduler`는 **폐기**한다 (PR #67 — execution_engine 단일 소유).
> `CycleDetectedError` 등 알고리즘 예외도 execution_engine이 소유. api_server는 GraphValidator의 `ValidationErrorResponse`만 그대로 응답으로 직렬화.

### 2.2 Routes (엔드포인트)

| 라우터 | 파일 경로 | 엔드포인트 | 설명 |
|--------|-----------|-----------|------|
| `workflows` | `src/routes/workflows.py` | `POST /workflows` | 워크플로우 생성 (WorkflowSchema 기반) |
| | | `GET /workflows/{id}` | 워크플로우 조회 |
| | | `PUT /workflows/{id}` | 워크플로우 수정 |
| | | `DELETE /workflows/{id}` | 워크플로우 삭제 |
| | | `POST /workflows/{id}/validate` | DAG 유효성 검증 → ValidationErrorResponse |
| | | `POST /workflows/{id}/execute` | 워크플로우 실행 시작 |
| `agents` | `src/routes/agents.py` | `POST /agents/sessions` | 에이전트 세션 생성 |
| | | `GET /agents/sessions/{id}/stream` | SSE 스트리밍 엔드포인트 (AnySSEFrame) |
| | | `POST /agents/sessions/{id}/messages` | 사용자 메시지 전송 |
| | | `GET /agents/sessions/{id}/state` | 현재 AgentState 조회 |
| `documents` | `src/routes/documents.py` | `POST /documents/upload` | 문서 업로드 |
| | | `GET /documents/{id}` | 문서 조회 |
| | | `POST /documents/{id}/analyze` | 문서 분석 요청 |
| `auth` | `src/routes/auth.py` | `POST /auth/login` | OAuth2 로그인 |
| | | `POST /auth/refresh` | 토큰 갱신 |
| | | `GET /auth/me` | 현재 사용자 정보 |
| `nodes` | `src/routes/nodes.py` | `GET /nodes/catalog` | 노드 카탈로그 조회 (NodeConfig[] — 56종, PR #68) |
| `skills` | `src/routes/skills.py` | `POST /skills/bootstrap`, `GET /skills` | REQ-013 후보 `skills_marketplace.SearchSkillsUseCase` |
| `marketplace` | `src/routes/marketplace.py` | `GET /marketplace`, `POST /marketplace/{id}/promote` | REQ-013 후보 PromoteToTeam/PromoteToCompany |
| `exec_control` | `src/routes/exec_control.py` | `POST /executions/{id}/cancel`, `/resume` | REQ-007 PauseResumeUseCase (Celery revoke + state transition) |
| `health` | `src/routes/health.py` | `GET /health` | DB(`SELECT 1`) + Redis + Orchestrator URL 연결성 점검 |

### 2.3 Services (Application Layer)

| 서비스 | 파일 경로 | 설명 |
|--------|-----------|------|
| `WorkflowService` | `src/services/workflow_service.py` | 워크플로우 CRUD — `WorkflowRepository`(modules/storage) 호출. **save 호출 직전 `permission_source.user_id`를 `WorkflowSchema.owner_user_id`로 명시 주입** (PR #66 v0.3.0, NOT NULL 방어) |
| `SSEStreamService` | `src/services/sse_stream_service.py` | Orchestrator Modal app의 SSE 응답(`text/event-stream`)을 **그대로 클라이언트로 패스스루**. 본 서비스가 LangGraph를 직접 호출하지 않음 |
| `AgentSessionService` | `src/services/agent_session_service.py` | 세션 생성/관리 — Orchestrator HTTP 호출은 `OrchestratorClient` 어댑터 위임. `langgraph_thread_id`는 orchestrator 발급분을 보관 |
| `AuthService` | `src/services/auth_service.py` | JWT 발급/검증, OAuth2 플로우 |

### 2.4 Infrastructure

| 컴포넌트 | 파일 경로 | 설명 |
|----------|-----------|------|
| `SSEEncoder` | `src/infrastructure/sse_encoder.py` | AnySSEFrame → `text/event-stream` 포맷 직렬화 |
| `DependencyContainer` | `src/infrastructure/container.py` | FastAPI Depends 기반 DI 컨테이너 |
| `ErrorHandlers` | `src/infrastructure/error_handlers.py` | 전역 예외 핸들러 (DomainError → HTTP 4xx/5xx) |
| `CORSMiddleware` | `src/infrastructure/middleware.py` | CORS 설정 (프론트엔드 Origin 허용) |
| `RateLimiter` | `src/infrastructure/rate_limiter.py` | 요청 속도 제한 미들웨어 |

### 2.5 Custom Exceptions

| 예외 | 설명 |
|------|------|
| `SessionNotFoundError` | 존재하지 않는 세션 접근 시 |
| `StreamClosedError` | 이미 닫힌 SSE 스트림에 쓰기 시도 시 |
| `OrchestratorUnavailableError` | OrchestratorClient HTTP 호출 실패(timeout / 5xx) — `ErrorFrame`으로 변환하여 클라이언트 전달 |

> `CycleDetectedError`는 api_server 미소유 — execution_engine 또는 `nodes_graph.GraphValidator` 측에서 정의/raise한다.

---

## 3. 합의된 변경사항 (클래스 다이어그램 교차분석)

| # | 합의 사항 | 영향 |
|---|-----------|------|
| 1 | DAGScheduler → **TopologicalScheduler** 개명 | 클래스명 변경. 그래프 알고리즘의 본질(위상정렬)을 정확히 반영 |
| 2 | SSE transport 스키마를 common_schemas로 이동 | API 서버는 transport 모듈 import만 하면 됨 (자체 정의 불필요) |
| 3 | ValidationErrorResponse를 common_schemas에서 관리 | 검증 에러 포맷 통일 (프론트엔드와 동일 스키마 공유) |
| 4 | ID 타입 = UUID (str 아님) | 모든 *_id 필드는 `uuid.UUID` 타입 사용 |
| 5 | Optional 필드 합집합 확장 전략 | 공유 스키마의 Optional 필드는 각 모듈에서 선택적으로 활용 |
| 6 | `scope` 필드 소문자 통일 (ADR-0006) | "private" / "team" / "public" (PascalCase 금지) |
| 7 | `database/` / `modules/storage/` / `modules/skills_marketplace/` 책임 분리 (ADR-0012 v3) | api_server는 storage(async Repository SSOT) + skills_marketplace(use_cases)를 모두 조립. `database/`는 런타임 호출 없음 (부팅 전 schema_migrations bootstrap) |
| 8 | EmbedderPort SSOT = `nodes_graph.domain.ports` (ADR-0013) | api_server에는 영향 없음 (sub-agent 측 의존). 참조용으로만 표기 |
| 9 | `IntentType` Enum SSOT = `common_schemas.enums` (v0.4.0, PR #72) | `ResultFrame.intent`는 `IntentType` 값으로 직렬화. 문자열 비교는 SSOT 위반 |
| 10 | `TopologicalScheduler` 단일 소유 = `execution_engine` (PR #67) | api_server `domain/topological_scheduler.py`는 폐기. Celery worker 내부에서 호출 |
| 11 | `workflow-manager` 모듈 도입 안 함 (ADR-0012 v3 영구 결정) | 워크플로우 CRUD는 라우터가 `dependencies/`에서 `WorkflowRepository`(modules/storage)를 직접 DI받아 호출 |
| 12 | Cloud SQL IAM 인증 표준 ([[sub_agent_cloud_sql_iam]]) | staging/prod에서 `DB_PASSWORD` 평문 DSN 금지. `INSTANCE_CONNECTION_NAME` + SA 이메일 + 런타임 토큰 |

---

## 4. 의존성 관계

```
services/api_server/
├── imports from ─────────────────────────────────────────┐
│   packages/common_schemas/python/                       │ (SSOT 엔티티/VO/Enum/agent_protocol — IntentType, AgentProtocolRequest 등)
│                                                         │
├── calls (via Port interface, in-process) ───────────────┐
│   modules/auth/application/                             │ (인증/인가 유스케이스)
│   modules/doc_parser/application/                       │ (문서 파싱 유스케이스)
│   modules/nodes_graph/                                  │ (ValidateGraph, SearchNodes, GraphValidator)
│   modules/toolset/application/                          │ (ListTools, ValidateToolConfig)
│   modules/storage/repositories/                         │ (WorkflowRepository, SessionRepository, AgentMemoryRepository 등 — ADR-0012 v3 ORM/Repository/Mapper SSOT)
│   modules/skills_marketplace/application/use_cases/     │ (SearchSkills, PromoteToTeam/Company — REQ-013 후보, ADR-0012 v3 신설)
│                                                         │
│   ※ workflow-manager 모듈은 도입하지 않음 (ADR-0012 v3) │
│     워크플로우 CRUD = 라우터 → WorkflowRepository 직접 호출 (조립은 dependencies/) │
│                                                         │
├── depends on (런타임 호출 없음) ──────────────────────────┐
│   database/                                             │ (REQ-001 — 순수 SQL 마이그레이션 + schema_migrations 부트스트랩, 배포 전 적용) │
│                                                         │
├── calls (via HTTP adapter, out-of-process) ─────────────┐
│   ai_agent Orchestrator Modal app                       │ (REQ-004 멀티 에이전트 — VPC 내부 HTTP) │
│     `services/api_server/src/adapters/orchestrator_client.py` │
│   ※ 4종 sub-agent(composer/skills_builder/personalization)는 orchestrator 내부 라우팅 │
│                                                         │
├── integrates with (broker only) ──────────────────────────┐
│   services/execution_engine/ (REQ-007)                  │ (Celery task dispatch만 — Redis broker 경유. 직접 import 0건) │
│                                                         │
└── consumed by ──────────────────────────────────────────┐
    services/frontend/ (REQ-010)                          │ (HTTP REST + SSE 클라이언트)
```

> **ai_agent in-process import 금지**: Sprint 3에서 ai_agent가 sub-agent별 Modal app으로 분리되었다 (`docs/specs/REQ-004-ai-agent.md` §0). api_server는 `modules/ai_agent/application/*`를 **직접 import하지 않는다**. 대신 `adapters/orchestrator_client.py`(HTTP 어댑터)가 Orchestrator Modal endpoint를 호출하며, SSE 응답을 그대로 클라이언트에 프록시한다.

### 4.1 DI 조립 규칙

- API 서버는 **조립(Composition Root)** 역할만 수행
- 모든 in-process 유스케이스는 Port 인터페이스를 통해 호출
- ai_agent는 **HTTP 어댑터(OrchestratorClient)** 만 노출. composition root에서 base URL과 timeout만 주입
- 구체 구현체는 `DependencyContainer`에서 주입
- **ORM 모델 직접 직렬화 금지** (ADR-0012 v3) — Repository를 통해 도메인 엔티티(common_schemas) 수신 후 응답 모델 변환
- **Workflow save 시점에 `owner_user_id` 명시 주입** (PR #66 v0.3.0) — `permission_source.user_id`를 `WorkflowSchema.owner_user_id`로 채운 뒤 `WorkflowRepository.save` 호출. 누락 시 modules/storage mapper가 ValueError raise (NOT NULL 방어)

### 4.2 ai_agent HTTP 어댑터 계약

`OrchestratorClient`는 `common_schemas.agent_protocol.AgentProtocolRequest/Response`로 직렬화하여 Orchestrator Modal app(`POST /v1/agent/route`)을 호출한다. 응답 SSE 스트림은 9종 프레임으로 디코딩되어 `SSEStreamService`가 그대로 클라이언트에 중계한다.

| 환경 변수 | 용도 |
|----------|------|
| `ORCHESTRATOR_URL` | Modal app endpoint (VPC 내부) |
| `ORCHESTRATOR_TIMEOUT_S` | HTTP 타임아웃 (기본 60s) |

> Personalization sub-agent의 `update_memory`/`cleanup` 흐름은 orchestrator가 내부 라우팅으로 처리한다 (PR #70). api_server는 Personalization Modal app을 **직접 호출하지 않는다**.

---

## 5. 디렉토리 구조 (최종)

```
services/api_server/
├── src/
│   ├── main.py                          # FastAPI app factory + Uvicorn 실행
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── workflows.py                 # /workflows 엔드포인트
│   │   ├── agents.py                    # /agents 엔드포인트 + SSE stream (orchestrator 패스스루)
│   │   ├── documents.py                 # /documents 엔드포인트
│   │   ├── nodes.py                     # /nodes/catalog 엔드포인트 (56종)
│   │   ├── skills.py                    # /skills (REQ-013 후보 skills_marketplace)
│   │   ├── marketplace.py               # /marketplace + /promote
│   │   ├── exec_control.py              # /executions/{id}/cancel|resume (REQ-007)
│   │   ├── health.py                    # /health (DB+Redis+Orchestrator 연결성)
│   │   └── auth.py                      # /auth 엔드포인트
│   ├── services/
│   │   ├── workflow_service.py          # owner_user_id 주입 + WorkflowRepository 호출
│   │   ├── sse_stream_service.py        # Orchestrator SSE 패스스루
│   │   ├── agent_session_service.py
│   │   └── auth_service.py
│   ├── adapters/
│   │   └── orchestrator_client.py       # ai_agent Orchestrator HTTP 어댑터 (Modal app)
│   ├── dependencies/
│   │   ├── container.py                 # DI 컨테이너 (Cloud SQL IAM async engine + Repository 조립)
│   │   └── repositories.py              # modules/storage Repository 인스턴스 제공
│   └── infrastructure/
│       ├── sse_encoder.py               # SSEFrame → text/event-stream
│       ├── error_handlers.py            # 전역 예외 핸들러
│       ├── middleware.py                # CORS, 로깅
│       └── rate_limiter.py              # 속도 제한
├── tests/
│   ├── test_routes_workflows.py
│   ├── test_routes_agents.py
│   ├── test_routes_health.py
│   ├── test_sse_encoder.py
│   └── conftest.py                      # 공용 fixture
├── pyproject.toml
└── README.md
```

> `src/domain/topological_scheduler.py`는 **폐기**(PR #67 단일 소유 정책). execution_engine에서만 보유.

---

## 6. SSE 스트리밍 프로토콜

### 6.1 연결 흐름 (Orchestrator HTTP 프록시)

Sprint 3 이후 ai_agent는 Modal app으로 분리되어 in-process LangGraph 호출이 없다. api_server는 Orchestrator Modal app의 SSE 응답을 **그대로 패스스루**한다.

```
Client                       API Server                    Orchestrator Modal app          Sub-agent Modal apps
  │                              │                                    │                            │
  ├─ GET /agents/sessions/{id}/stream ─►│                                    │                            │
  │      Accept: text/event-stream│                                    │                            │
  │                              ├── POST /v1/agent/route ──────────►│                            │
  │                              │   (AgentProtocolRequest)            │                            │
  │                              │                                    ├── HTTP → composer/skills_builder/personalization
  │                              │                                    │   (내부 supervisor 라우팅)
  │                              │                                    │◄── SSE stream ─────────────┤
  │                              │◄── SSE text/event-stream pass-through                            │
  │◄── SessionFrame ─────────────┤                                    │                            │
  │◄── AgentNodeFrame ───────────┤                                    │                            │
  │◄── RationaleDeltaFrame ──────┤                                    │                            │
  │◄── SlotFillQuestionFrame ────┤                                    │                            │
  │                              │                                    │                            │
  ├─ POST /agents/sessions/{id}/messages─►│── POST /v1/agent/route ──────────►│                            │
  │                              │                                    │                            │
  │◄── DraftSpecDeltaFrame ──────┤                                    │                            │
  │◄── ResultFrame (intent: IntentType, payload) ─────────────────────│                            │
  │      OR                      │                                    │                            │
  │◄── ErrorFrame (code, message)┤                                    │                            │
```

> `SSEStreamService`는 LangGraph를 **직접 호출하지 않는다**. Orchestrator의 `text/event-stream` 응답을 스트리밍으로 받아 클라이언트에 중계한다.
> `langgraph_thread_id`는 Orchestrator(Composer Modal app 내부)가 발급하며, api_server는 `SessionFrame`에서 추출해 클라이언트 식별자로 보관한다.

### 6.2 SSE 인코딩 형식

```
event: {frame_type}
data: {JSON serialized frame}

```

예시:
```
event: session
data: {"frame_type":"session","session_id":"550e8400-...","langgraph_thread_id":"6ba7b810-..."}

event: rationale_delta
data: {"frame_type":"rationale_delta","delta":"사용자의 요청을 분석하면"}

event: result
data: {"frame_type":"result","intent":"draft","payload":{"workflow_id":"..."}}

```
