# REQ-007 Execution Engine -- 구현 명세

> 담당: 황대원  
> 서비스 경로: `services/execution_engine/`  
> 의존 패키지: `common_schemas >= 0.1.0`, `celery >= 5.3`, `langgraph >= 0.1`

---

## common_schemas에서 import할 클래스

| 클래스 | 소스 모듈 | 용도 |
|--------|-----------|------|
| `WorkflowSchema` | `common_schemas.workflow` | 워크플로우 정의 (노드 + 연결 그래프). TopologicalScheduler의 입력 |
| `NodeInstance` | `common_schemas.workflow` | 워크플로우 내 개별 노드 인스턴스 (parameters, credential_id, position) |
| `NodeConfig` | `common_schemas.workflow` | 노드 타입 정의 (input/output/parameter schema, risk_level) |
| `Edge` | `common_schemas.workflow` | 노드 간 연결 (from_instance_id -> to_instance_id) |
| `ExecutionStatus` | `common_schemas.enums` | 실행 상태 enum (RUNNING, PAUSED, COMPLETED, FAILED) |
| `ErrorCode` | `common_schemas.enums` | 에러 코드 enum (E_CYCLE_DETECTED, E_ISOLATED_NODE 등) |
| `HandoffPayload` | `common_schemas.handoff` | REQ-004 QA 통과 후 핸드오프 수신 페이로드 (direction, error_codes, state_data) |
| `EvaluationResult` | `common_schemas.handoff` | QA Evaluator 점수/통과 여부 (score, pass_flag, reason, feedback) |
| `Position` | `common_schemas.workflow` | 노드 위치 좌표 (UI 렌더링용) |
| `RiskLevel` | `common_schemas.enums` | 노드 위험 등급 (Low/Medium/High/Restricted) |
| `ExecutionError` | `common_schemas.exceptions` | 실행 도메인 예외 |
| `ValidationError` | `common_schemas.exceptions` | 그래프 검증 실패 예외 |

### import 예시

```python
from common_schemas import (
    WorkflowSchema,
    NodeInstance,
    NodeConfig,
    Edge,
    ExecutionStatus,
    ErrorCode,
    HandoffPayload,
    EvaluationResult,
    RiskLevel,
    ExecutionError,
    ValidationError,
)
```

---

## 이 모듈에서 구현할 클래스

### Domain Layer (`domain/`)

#### domain/entities

| 클래스 | 필드 | 설명 |
|--------|------|------|
| `ExecutionContext` | `execution_id: UUID`, `workflow_id: UUID`, `user_id: UUID`, `trigger_type: Literal["manual", "scheduled", "handoff", "resume"]`, `started_at: datetime`, `parameters: dict[str, Any]`, `task_queue_id: Optional[str]` | 워크플로우 실행 컨텍스트 (실행 한 번의 메타정보). `task_queue_id`는 워커 pickup 시점에 broker가 부여한 task id — `ExecuteWorkflowUseCase`가 첫 INSERT에 그대로 영속화 |
| `ExecutionResult` | `execution_id: UUID`, `workflow_id: UUID`, `user_id: Optional[UUID]`, `status: ExecutionStatus`, `node_results: list[NodeResult]`, `started_at: datetime`, `completed_at: Optional[datetime]`, `error: Optional[str]`, `task_queue_id: Optional[str]` | 워크플로우 전체 실행 결과 (user_id: 실행 발신자 추적). `task_queue_id`는 cancel 시 `TaskQueuePort.revoke` 인자로 사용 — 컬럼명/필드명은 broker 비종속 (Celery → 다른 큐로 교체 시 adapter만 수정). `mark_cancelled()` 메서드는 status=CANCELLED + completed_at 자동 세팅 |
| `NodeResult` | `node_instance_id: UUID`, `status: Literal["succeeded", "failed", "cancelled", "skipped"]`, `output: dict[str, Any]`, `started_at: datetime`, `completed_at: datetime`, `retry_count: int`, `error: Optional[str]` | 개별 노드 실행 결과 |
| `ExecutionLevel` | `level: int`, `nodes: list[NodeInstance]` | 위상 정렬 결과의 한 실행 레벨 (같은 레벨 = 병렬 실행 가능) |
| `RetryPolicy` | `max_retries: int`, `backoff_base_seconds: float`, `retryable_errors: list[str]` | 노드 재시도 정책 VO |
| `NodeExecutionState` | *(common_schemas.workflow에서 import)* `node_instance_id: UUID`, `status: Literal["pending", "running", "succeeded", "failed", "retrying", "cancelled"]`, `attempt: int`, `last_error: Optional[str]` | 노드 실행 상태 추적 (SSOT: common_schemas에 정의됨) |

#### domain/services

| 서비스 클래스 | 메서드 | 설명 |
|-------------|--------|------|
| `TopologicalScheduler` | `schedule(workflow: WorkflowSchema) -> list[ExecutionLevel]` | Kahn's algorithm으로 위상 정렬. 동일 in-degree 노드를 같은 레벨로 묶어 병렬 실행 순서 결정 |
| | `validate_dag(workflow: WorkflowSchema) -> None` | 순환 참조 검출. 발견 시 `ValidationError(code=E_CYCLE_DETECTED)` 발생 |
| `RetryManager` | `should_retry(error: Exception, policy: RetryPolicy, attempt: int) -> bool` | 재시도 가능 여부 판정 |
| | `get_backoff_delay(policy: RetryPolicy, attempt: int) -> float` | 지수 백오프 지연 시간 계산 |
| `ExecutionOrchestrator` | `plan(workflow: WorkflowSchema) -> list[ExecutionLevel]` | 그래프 검증(validate_graph + validate_dag) 후 위상 정렬. 순수 비즈니스 규칙만 캡슐화 (Port 의존 없음) |
| | `has_failures(level_results: list[NodeResult]) -> bool` | 레벨 실행 결과 중 실패 노드 존재 여부 판정 |
| | `validate_state_transition(current: ExecutionStatus, target: ExecutionStatus) -> None` | 상태 전이 유효성 검증. 위반 시 ExecutionError 발생 |

#### domain/ports (ABC 인터페이스)

| 포트 | 메서드 | 설명 |
|------|--------|------|
| `WorkflowRepositoryPort` | `get(workflow_id: UUID) -> WorkflowSchema` | 워크플로우 정의 조회 |
| | `get_node_config(node_id: UUID) -> NodeConfig` | 노드 타입 설정 조회 |
| `ExecutionRepositoryPort` | `save(result: ExecutionResult) -> None` | 실행 결과 영속화 |
| | `get(execution_id: UUID) -> ExecutionResult` | 실행 결과 조회 |
| | `update_node_state(execution_id: UUID, state: NodeExecutionState) -> None` | 노드 상태 업데이트 |
| `NodeExecutorPort` | `execute(node: NodeInstance, config: NodeConfig, inputs: dict[str, Any]) -> dict[str, Any]` | 개별 노드 실행 (Tool 호출 또는 LLM Agent 디스패치) |
| `TaskQueuePort` | `dispatch(task_name: str, args: dict) -> str` | 일반 task 발행 (legacy / adapter 내부용) |
| | `dispatch_chord(tasks: list[dict], callback: str) -> str` | 병렬 그룹 + 콜백 (chord) |
| | `dispatch_workflow(*, execution_id: UUID, workflow_id: UUID, user_id: UUID \| None, trigger_type: Literal["manual","scheduled","handoff","resume"], parameters: dict \| None = None) -> str` | **의미적** 메서드. application 레이어가 broker-specific task name/queue를 몰라야 함 — adapter가 직렬화 책임. 반환 = 새 `task_queue_id` |
| | `revoke(task_id: str, *, terminate: bool = True) -> None` | 발행된 task 취소. Celery 어댑터는 `app.control.revoke(task_id, terminate=..., signal="SIGTERM")` 호출 |
| `CredentialProviderPort` | `get_credential(credential_id: UUID, user_id: UUID) -> dict[str, str]` | REQ-002 자격증명 주입 (복호화된 credential 반환) |
| `EventPublisherPort` | `publish_status(execution_id: UUID, status: ExecutionStatus) -> None` | SSE로 프론트엔드에 상태 전파 |
| | `publish_node_complete(execution_id: UUID, node_result: NodeResult) -> None` | 노드 완료 이벤트 발행 |

### Application Layer (`application/`)

| 유스케이스 | Input -> Output | 설명 |
|-----------|----------------|------|
| `ExecuteWorkflowUseCase` | `(workflow_id: UUID, context: ExecutionContext) -> ExecutionResult` | 전체 오케스트레이션: 워크플로우 조회 -> DAG 검증 -> 위상 정렬 -> 레벨별 실행 -> 결과 저장. `context.task_queue_id`는 첫 `ExecutionResult` 인스턴스 생성 시 그대로 전달 → 단일 transaction 영속화 |
| `DispatchNodeUseCase` | `(node: NodeInstance, config: NodeConfig, inputs: dict, user_id: UUID, execution_id: UUID) -> NodeResult` | 단일 노드 실행: credential 주입(__user_id__ + __credentials__) -> NodeExecutor 호출 -> 재시도 처리 -> 결과 반환 |
| `HandleHandoffUseCase` | `(payload: HandoffPayload) -> ExecutionResult` | REQ-004 QA 통과 후 핸드오프 수신: WorkflowSchema 조회 -> ExecuteWorkflowUseCase 위임 |
| `PauseResumeUseCase` | `(execution_id: UUID, action: Literal["pause", "resume", "cancel"], approval: Optional[dict]) -> None` | 일시 중지 / 재개 / 취소. `cancel` 시 `task_queue.revoke()` 호출 후 status=CANCELLED 마킹. `resume` 시 `task_queue.dispatch_workflow()` → 새 task_queue_id로 갱신해 옛 task에 대한 revoke를 방지 |
| `EvaluateAndRefineUseCase` | `(execution_id: UUID, evaluation: EvaluationResult) -> Optional[ExecutionResult]` | QA score < 8 시 Self-Refine 재실행 (최대 3회) |

### Infrastructure/Adapter Layer (`adapters/`)

| 어댑터 클래스 | 구현 포트 | 설명 |
|-------------|----------|------|
| `CeleryAdapter` | `TaskQueuePort` | Celery task 등록, dispatch, chord 실행 |
| `CeleryWorkerTasks` | -- | `@app.task` 데코레이터 태스크 정의 (execute_workflow, execute_node) |
| `SandboxExecutor` | `NodeExecutorPort` (부분) | gVisor/nsjail 기반 코드 실행 샌드박스 |
| `LangGraphDispatcher` | `NodeExecutorPort` (부분) | AI 에이전트 노드 -> REQ-004 LangGraph StateGraph 연동 |
| `ToolsetExecutor` | `NodeExecutorPort` (부분) | REQ-005 toolset 모듈 ExecuteToolUseCase 연동 |
| `PostgresWorkflowRepository` | `WorkflowRepositoryPort` | PostgreSQL에서 WorkflowSchema 조회 |
| `PostgresExecutionRepository` | `ExecutionRepositoryPort` | 실행 결과/노드 상태 PostgreSQL 저장 |
| `VaultCredentialProvider` | `CredentialProviderPort` | REQ-002 CredentialStore 연동 (AES-256 복호화) |
| `SSEEventPublisher` | `EventPublisherPort` | Redis Pub/Sub -> SSE 스트림으로 상태 전파 |

#### dependencies/ (DI 컨테이너)

| 클래스 | 설명 |
|--------|------|
| `Container` | 의존성 주입 컨테이너. 포트 -> 어댑터 바인딩, Celery app 설정 |

---

## 합의된 변경사항 (클래스 다이어그램 교차분석)

| 항목 | 변경 내용 | 근거 |
|------|----------|------|
| `DAGScheduler` -> `TopologicalScheduler` 개명 | DAG는 자료구조명이지 알고리즘이 아님. Kahn's algorithm 기반이므로 TopologicalScheduler로 확정 | HIGH-002 교차분석 + 팀 투표 확정 |
| LangGraph StateGraph + Celery 2-Tier 구조 | 워크플로우 실행(사용자 정의)은 Celery 태스크, AI Agent 내부 그래프(REQ-004)는 LangGraph. 역할 분리 확정 | HIGH-003 아키텍처 결정 |
| 핸드오프 수신 인터페이스 추가 | REQ-004 QA 통과 후 HandoffPayload -> WorkflowRepository.get() -> 디스패치 흐름 확정 | HIGH-004 |
| credential_id -> REQ-002 주입 | NodeInstance.credential_id를 통해 CredentialProviderPort가 런타임에 복호화된 자격증명 주입 | MEDIUM-001 |
| `ExecutionStatus` enum common_schemas 사용 | 자체 정의 삭제, common_schemas의 ExecutionStatus(RUNNING/PAUSED/COMPLETED/FAILED) 사용 | HIGH-001 SSOT |
| WorkflowSchema.validate_graph() 활용 | 실행 전 재검증 시 WorkflowSchema 내장 validate_graph() 호출 + TopologicalScheduler.validate_dag() 보완 | MEDIUM-005 |

---

## 의존성 관계

```
services/execution_engine
├── depends on ─────────────────────────────────────────────────────────────
│   ├── packages/common_schemas   (WorkflowSchema, NodeInstance, Edge, ExecutionStatus, HandoffPayload, EvaluationResult, ErrorCode)
│   ├── modules/nodes_graph       (REQ-003: GraphValidator -- 실행 전 재검증)
│   ├── modules/toolset           (REQ-005: ExecuteToolUseCase -- 외부 도구 실행)
│   ├── modules/ai_agent          (REQ-004: LangGraph 에이전트 노드 실행)
│   ├── modules/auth              (REQ-002: CredentialStore -- 자격증명 복호화)
│   └── modules/storage           (REQ-001: WorkflowRepository, ExecutionRepository)
│
├── depended by ────────────────────────────────────────────────────────────
│   ├── services/api_server       (Celery task dispatch: execute_workflow.delay())
│   └── modules/ai_agent          (REQ-004 QA 통과 후 핸드오프 발신 -> 본 서비스가 수신)
│
└── runtime dependencies ───────────────────────────────────────────────────
    ├── Redis                     (Celery broker + result backend + SSE pub/sub)
    ├── PostgreSQL                (workflow 정의, execution 결과 저장)
    └── gVisor / nsjail           (샌드박스 코드 실행, 선택적)
```

### 패키지 설치 의존성 (pyproject.toml)

```toml
[project]
dependencies = [
    "common_schemas",
    "pydantic>=2.0",
    "celery[redis]>=5.3",
    "langgraph>=0.1",
    "redis>=5.0",
    "sqlalchemy>=2.0",
    "psycopg[binary]>=3.1",
]
```

---

## 디렉토리 구조 (목표)

```
services/execution_engine/
├── Dockerfile
├── pyproject.toml
├── src/
│   ├── __init__.py
│   ├── main.py                         ← Celery app 초기화
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── entities/
│   │   │   ├── __init__.py
│   │   │   ├── execution_context.py    ← ExecutionContext
│   │   │   ├── execution_result.py     ← ExecutionResult, NodeResult
│   │   │   ├── execution_level.py      ← ExecutionLevel
│   │   │   └── retry_policy.py         ← RetryPolicy
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── topological_scheduler.py  ← TopologicalScheduler (Kahn's algorithm)
│   │   │   ├── retry_manager.py          ← RetryManager
│   │   │   └── execution_orchestrator.py ← ExecutionOrchestrator
│   │   └── ports/
│   │       ├── __init__.py
│   │       ├── workflow_repository_port.py
│   │       ├── execution_repository_port.py
│   │       ├── node_executor_port.py
│   │       ├── task_queue_port.py
│   │       ├── credential_provider_port.py
│   │       └── event_publisher_port.py
│   ├── application/
│   │   ├── __init__.py
│   │   └── use_cases/
│   │       ├── __init__.py
│   │       ├── execute_workflow.py       ← ExecuteWorkflowUseCase
│   │       ├── dispatch_node.py          ← DispatchNodeUseCase
│   │       ├── handle_handoff.py         ← HandleHandoffUseCase
│   │       ├── pause_resume.py           ← PauseResumeUseCase
│   │       └── evaluate_and_refine.py    ← EvaluateAndRefineUseCase
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── celery_adapter.py            ← CeleryAdapter
│   │   ├── celery_tasks.py              ← CeleryWorkerTasks (@app.task)
│   │   ├── sandbox_executor.py          ← SandboxExecutor
│   │   ├── langgraph_dispatcher.py      ← LangGraphDispatcher
│   │   ├── toolset_executor.py          ← ToolsetExecutor
│   │   ├── postgres_workflow_repo.py    ← PostgresWorkflowRepository
│   │   ├── postgres_execution_repo.py   ← PostgresExecutionRepository
│   │   ├── vault_credential_provider.py ← VaultCredentialProvider
│   │   └── sse_event_publisher.py       ← SSEEventPublisher
│   └── dependencies/
│       ├── __init__.py
│       └── container.py                 ← DI Container
└── tests/
    ├── conftest.py
    ├── unit/
    │   ├── test_topological_scheduler.py
    │   ├── test_retry_manager.py
    │   ├── test_execute_workflow.py
    │   └── test_dispatch_node.py
    └── integration/
        └── .gitkeep
```

---

## 실행 흐름 상세

```
1. API Server -> Celery Task (execute_workflow.delay)
2. CeleryWorkerTasks.execute_workflow(workflow_id, context)
3.   -> ExecuteWorkflowUseCase.execute()
4.      -> WorkflowRepositoryPort.get(workflow_id) -> WorkflowSchema
5.      -> WorkflowSchema.validate_graph() (기본 검증)
6.      -> TopologicalScheduler.validate_dag() (순환 참조 검증)
7.      -> TopologicalScheduler.schedule() -> list[ExecutionLevel]
8.      -> For each level:
9.          -> TaskQueuePort.dispatch_chord(level.nodes)
10.         -> For each node (병렬):
11.             -> DispatchNodeUseCase.execute(node, config, inputs)
12.                -> CredentialProviderPort.get_credential(credential_id)
13.                -> NodeExecutorPort.execute(node, config, inputs)
14.                   -> ToolsetExecutor (일반 노드) 또는
15.                   -> LangGraphDispatcher (AI 에이전트 노드) 또는
16.                   -> SandboxExecutor (코드 실행 노드)
17.                -> RetryManager (실패 시 재시도 판정)
18.             -> EventPublisherPort.publish_node_complete()
19.         -> 레벨 완료 대기
20.      -> ExecutionRepositoryPort.save(result)
21.      -> EventPublisherPort.publish_status(COMPLETED)
```

---

## 핸드오프 수신 흐름 (REQ-004 -> REQ-007)

```
1. REQ-004 AI Agent: QA Evaluator score >= 8 (통과)
2. REQ-004 -> HandoffPayload 생성 (direction="forward", state_data={workflow_id, ...})
3. HandleHandoffUseCase.execute(payload)
4.   -> WorkflowRepositoryPort.get(payload.state_data["workflow_id"])
5.   -> ExecutionContext 생성 (trigger_type="handoff")
6.   -> ExecuteWorkflowUseCase에 위임
```

---

## 구현 우선순위

| 순서 | 대상 | 이유 |
|------|------|------|
| 1 | `domain/entities/` (ExecutionContext, ExecutionResult, NodeResult, ExecutionLevel) | 모든 레이어가 참조하는 핵심 엔티티 |
| 2 | `domain/services/TopologicalScheduler` | Kahn's algorithm 핵심 로직. 단위 테스트 우선 작성 |
| 3 | `domain/ports/` (모든 ABC 인터페이스) | 어댑터 병렬 개발의 전제 조건 |
| 4 | `application/use_cases/ExecuteWorkflowUseCase` | 핵심 오케스트레이션 유스케이스 |
| 5 | `adapters/celery_adapter.py` + `celery_tasks.py` | Celery 인프라 연동 |
| 6 | `adapters/toolset_executor.py` | REQ-005 연동 (MVP 필수) |
| 7 | `adapters/langgraph_dispatcher.py` | REQ-004 연동 (AI 노드) |
| 8 | 나머지 어댑터 (persistence, credential, SSE) | 인프라 레이어 완성 |

---

## Celery 큐 설계

| 큐 이름 | 라우팅 키 | 용도 | 동시성 |
|---------|-----------|------|--------|
| `default` | `workflow.node.default` | 일반 노드 (DB 조회, 데이터 처리) | 4 |
| `llm` | `workflow.node.llm` | LLM 추론 노드 (Gemma4 호출) | 2 |
| `external_api` | `workflow.node.external` | 외부 API 호출 (Google, Slack 등) | 4 |

노드의 `NodeConfig.category` 값에 따라 큐 라우팅:
- `category == "ai"` -> `llm` 큐
- `category == "external"` -> `external_api` 큐
- 그 외 -> `default` 큐
