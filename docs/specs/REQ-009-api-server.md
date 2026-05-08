# REQ-009 API Server — 구현 명세

- **담당자**: 황대원
- **모듈 경로**: `services/api_server/`
- **기술 스택**: Python 3.11+, FastAPI, Uvicorn, SSE (Server-Sent Events)
- **아키텍처 계층**: Interface Adapters (Inbound — HTTP → Use Case)

---

## 1. common_schemas에서 import할 클래스

### 1.1 Python import (from common_schemas)

| 클래스/타입 | 소스 모듈 | 용도 |
|------------|-----------|------|
| `WorkflowSchema` | `workflow` | 워크플로우 CRUD 엔드포인트 요청/응답 직렬화 |
| `NodeInstance` | `workflow` | 워크플로우 내 노드 인스턴스 직렬화, TopologicalScheduler 입력 |
| `NodeConfig` | `workflow` | 노드 카탈로그 조회 응답 |
| `Edge` | `workflow` | 워크플로우 그래프 연결 정보, TopologicalScheduler 입력 |
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
| `AgentMode` | `enums` | 에이전트 모드 열거형 (onboarding/wizard/edit/general/security) |

### 1.2 import 코드 예시

```python
from common_schemas import (
    WorkflowSchema, NodeInstance, NodeConfig, Edge, Position,
    AgentState,
    SSEFrame, SessionFrame, AgentNodeFrame, RationaleDeltaFrame,
    SlotFillQuestionFrame, DraftSpecDeltaFrame, ResultFrame, ErrorFrame,
    AnySSEFrame,
    ValidationErrorItem, ValidationErrorResponse,
    ExecutionStatus, AgentMode,
)
```

---

## 2. 이 모듈에서 구현할 클래스/컴포넌트

### 2.1 Domain / Core

| 클래스 | 파일 경로 | 설명 |
|--------|-----------|------|
| `TopologicalScheduler` | `src/domain/topological_scheduler.py` | Kahn's algorithm 기반 워크플로우 노드 실행 순서 결정. `NodeInstance[]` + `Edge[]`를 입력받아 실행 레벨별 그룹(병렬 가능 노드 집합) 반환 |

#### TopologicalScheduler 상세

```python
class TopologicalScheduler:
    """Kahn's topological sort를 사용한 워크플로우 노드 실행 순서 결정기.
    
    구 명칭: DAGScheduler (클래스 다이어그램 교차분석에서 TopologicalScheduler로 개명 확정)
    """
    
    def schedule(self, nodes: list[NodeInstance], edges: list[Edge]) -> list[list[UUID]]:
        """노드를 위상정렬하여 실행 레벨별 그룹으로 반환.
        
        Returns:
            list[list[UUID]]: 각 내부 리스트는 동일 레벨(병렬 실행 가능)의 instance_id 집합
        
        Raises:
            CycleDetectedError: 그래프에 순환이 있을 때
        """
        ...
    
    def validate_dag(self, nodes: list[NodeInstance], edges: list[Edge]) -> ValidationErrorResponse:
        """DAG 유효성 검증 (순환, 고립 노드, 중복 ID 등)."""
        ...
```

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
| `nodes` | `src/routes/nodes.py` | `GET /nodes/catalog` | 노드 카탈로그 조회 (NodeConfig[]) |

### 2.3 Services (Application Layer)

| 서비스 | 파일 경로 | 설명 |
|--------|-----------|------|
| `WorkflowService` | `src/services/workflow_service.py` | 워크플로우 CRUD + TopologicalScheduler 호출 |
| `SSEStreamService` | `src/services/sse_stream_service.py` | LangGraph 실행 결과를 AnySSEFrame으로 변환하여 SSE 스트리밍 |
| `AgentSessionService` | `src/services/agent_session_service.py` | 에이전트 세션 생성/관리, LangGraph thread 연동 |
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
| `CycleDetectedError` | TopologicalScheduler에서 순환 감지 시 발생 |
| `SessionNotFoundError` | 존재하지 않는 세션 접근 시 |
| `StreamClosedError` | 이미 닫힌 SSE 스트림에 쓰기 시도 시 |

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

---

## 4. 의존성 관계

```
services/api_server/
├── imports from ─────────────────────────────────────────┐
│   packages/common_schemas/python/                       │ (SSOT 엔티티/VO/Enum)
│                                                         │
├── calls (via Port interface) ───────────────────────────┐
│   modules/ai_agent/application/                         │ (에이전트 세션 유스케이스)
│   modules/workflow-manager/application/                  │ (워크플로우 CRUD 유스케이스)
│   modules/doc_parser/application/                       │ (문서 파싱 유스케이스)
│   modules/auth/application/                             │ (인증/인가 유스케이스)
│   modules/storage/                                      │ (Repository 구현체)
│                                                         │
├── integrates with ──────────────────────────────────────┐
│   services/execution_engine/ (REQ-007)                  │ (워크플로우 실행 위임)
│                                                         │
└── consumed by ──────────────────────────────────────────┐
    services/frontend/ (REQ-010)                          │ (HTTP/SSE 클라이언트)
```

### 4.1 DI 조립 규칙

- API 서버는 **조립(Composition Root)** 역할만 수행
- 모든 유스케이스는 Port 인터페이스를 통해 호출
- 구체 구현체는 `DependencyContainer`에서 주입

---

## 5. 디렉토리 구조 (최종)

```
services/api_server/
├── src/
│   ├── main.py                          # FastAPI app factory + Uvicorn 실행
│   ├── domain/
│   │   └── topological_scheduler.py     # TopologicalScheduler (Kahn's sort)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── workflows.py                 # /workflows 엔드포인트
│   │   ├── agents.py                    # /agents 엔드포인트 + SSE stream
│   │   ├── documents.py                 # /documents 엔드포인트
│   │   ├── nodes.py                     # /nodes/catalog 엔드포인트
│   │   └── auth.py                      # /auth 엔드포인트
│   ├── services/
│   │   ├── workflow_service.py
│   │   ├── sse_stream_service.py
│   │   ├── agent_session_service.py
│   │   └── auth_service.py
│   └── infrastructure/
│       ├── container.py                 # DI 컨테이너
│       ├── sse_encoder.py               # SSEFrame → text/event-stream
│       ├── error_handlers.py            # 전역 예외 핸들러
│       ├── middleware.py                # CORS, 로깅
│       └── rate_limiter.py              # 속도 제한
├── tests/
│   ├── test_topological_scheduler.py
│   ├── test_routes_workflows.py
│   ├── test_routes_agents.py
│   ├── test_sse_encoder.py
│   └── conftest.py                      # 공용 fixture
├── pyproject.toml
└── README.md
```

---

## 6. SSE 스트리밍 프로토콜

### 6.1 연결 흐름

```
Client                              API Server                    LangGraph
  │                                      │                            │
  ├─ GET /agents/sessions/{id}/stream ──►│                            │
  │      Accept: text/event-stream       │                            │
  │                                      ├─── create thread ─────────►│
  │◄──── SessionFrame (session_id) ──────┤◄── thread_id ─────────────┤
  │                                      │                            │
  │◄──── AgentNodeFrame ─────────────────┤◄── node transition ───────┤
  │◄──── RationaleDeltaFrame (delta) ────┤◄── token stream ──────────┤
  │◄──── SlotFillQuestionFrame ──────────┤◄── need input ────────────┤
  │                                      │                            │
  ├─ POST /agents/sessions/{id}/messages─►│── user reply ────────────►│
  │                                      │                            │
  │◄──── DraftSpecDeltaFrame ────────────┤◄── spec update ───────────┤
  │◄──── ResultFrame (intent, payload) ──┤◄── final result ──────────┤
  │      OR                              │                            │
  │◄──── ErrorFrame (code, message) ─────┤◄── error ─────────────────┤
```

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
