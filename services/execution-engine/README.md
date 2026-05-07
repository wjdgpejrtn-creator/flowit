# execution-engine

> REQ-007: Celery 워커, TopologicalScheduler + LangGraph 2-Tier 실행 엔진
>
> 구현 명세 → [`docs/specs/REQ-007-execution-engine.md`](../../docs/specs/REQ-007-execution-engine.md)

## 설치

```bash
pip install -e services/execution-engine
pip install -e "services/execution-engine[dev]"
```

## 실행

```bash
celery -A src.main worker --loglevel=info --concurrency=4
celery -A src.main beat --loglevel=info
```

## Quick Start

```python
from execution_engine.src.domain.entities import (
    ExecutionContext, ExecutionResult, NodeResult, ExecutionLevel, RetryPolicy, NodeExecutionState,
)
from execution_engine.src.domain.services import (
    TopologicalScheduler, RetryManager, ExecutionOrchestrator,
)
from execution_engine.src.domain.ports import (
    WorkflowRepositoryPort, ExecutionRepositoryPort, NodeExecutorPort,
    TaskQueuePort, CredentialProviderPort, EventPublisherPort,
)
from execution_engine.src.application.use_cases import (
    ExecuteWorkflowUseCase, DispatchNodeUseCase, HandleHandoffUseCase,
    PauseResumeUseCase, EvaluateAndRefineUseCase,
)
```

## Public API

### domain/entities

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `ExecutionContext` | `execution_id: UUID`, `workflow_id: UUID`, `user_id: UUID`, `trigger_type: Literal["manual","scheduled","handoff"]`, `started_at: datetime`, `parameters: dict` | 실행 컨텍스트 (1회 실행의 메타정보) |
| `ExecutionResult` | `execution_id: UUID`, `workflow_id: UUID`, `status: ExecutionStatus`, `node_results: list[NodeResult]`, `started_at: datetime`, `completed_at: Optional[datetime]`, `error: Optional[str]` | 워크플로우 전체 실행 결과 |
| `NodeResult` | `node_instance_id: UUID`, `status: Literal["succeeded","failed","cancelled","skipped"]`, `output: dict`, `retry_count: int`, `error: Optional[str]` | 개별 노드 실행 결과 |
| `ExecutionLevel` | `level: int`, `nodes: list[NodeInstance]` | 위상 정렬 결과의 한 레벨 (같은 레벨 = 병렬 실행) |
| `RetryPolicy` | `max_retries: int`, `backoff_base_seconds: float`, `retryable_errors: list[str]` | 노드 재시도 정책 (VO) |
| `NodeExecutionState` | `node_instance_id: UUID`, `status: Literal["pending","running","succeeded","failed","retrying","cancelled"]`, `attempt: int`, `last_error: Optional[str]` | 노드 실행 상태 추적 |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `TopologicalScheduler` | `schedule(workflow: WorkflowSchema) → list[ExecutionLevel]` | Kahn's algorithm 위상 정렬. 동일 in-degree 노드를 같은 레벨로 묶어 병렬 순서 결정 |
| | `validate_dag(workflow: WorkflowSchema) → None` | 순환 참조 검출. 발견 시 `ValidationError(E_CYCLE_DETECTED)` |
| `RetryManager` | `should_retry(error: Exception, policy: RetryPolicy, attempt: int) → bool` | 재시도 가능 여부 판정 |
| | `get_backoff_delay(policy: RetryPolicy, attempt: int) → float` | 지수 백오프 지연 계산 |
| `ExecutionOrchestrator` | `run(workflow: WorkflowSchema, context: ExecutionContext) → ExecutionResult` | 레벨별 순차, 레벨 내 병렬 실행 오케스트레이션 |
| | `pause(execution_id: UUID) → None` | HITL 노드 일시 중지 |
| | `resume(execution_id: UUID, approval: dict) → None` | 사용자 승인 후 재개 |

### domain/ports (인터페이스)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `WorkflowRepositoryPort` | `get(workflow_id: UUID) → WorkflowSchema` | `adapters/postgres_workflow_repo.py` |
| | `get_node_config(node_id: UUID) → NodeConfig` | |
| `ExecutionRepositoryPort` | `save(result: ExecutionResult) → None` | `adapters/postgres_execution_repo.py` |
| | `get(execution_id: UUID) → ExecutionResult` | |
| | `update_node_state(execution_id: UUID, state: NodeExecutionState) → None` | |
| `NodeExecutorPort` | `execute(node: NodeInstance, config: NodeConfig, inputs: dict) → dict` | `adapters/` (Toolset/LangGraph/Sandbox) |
| `TaskQueuePort` | `dispatch(task_name: str, args: dict) → str` | `adapters/celery_adapter.py` |
| | `dispatch_chord(tasks: list[dict], callback: str) → str` | |
| `CredentialProviderPort` | `get_credential(credential_id: UUID, user_id: UUID) → dict[str, str]` | `adapters/vault_credential_provider.py` |
| `EventPublisherPort` | `publish_status(execution_id: UUID, status: ExecutionStatus) → None` | `adapters/sse_event_publisher.py` |
| | `publish_node_complete(execution_id: UUID, node_result: NodeResult) → None` | |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ExecuteWorkflowUseCase` | `workflow_id: UUID, context: ExecutionContext → ExecutionResult` | 전체 오케스트레이션: 조회→DAG검증→위상정렬→레벨별실행→저장 |
| `DispatchNodeUseCase` | `node: NodeInstance, config: NodeConfig, inputs: dict → NodeResult` | 단일 노드: credential주입→NodeExecutor호출→재시도→결과 |
| `HandleHandoffUseCase` | `payload: HandoffPayload → ExecutionResult` | REQ-004 QA 통과 후 핸드오프 수신 → ExecuteWorkflowUseCase 위임 |
| `PauseResumeUseCase` | `execution_id: UUID, action: Literal["pause","resume"], approval: Optional[dict] → None` | HITL 노드 일시 중지/재개 |
| `EvaluateAndRefineUseCase` | `execution_id: UUID, evaluation: EvaluationResult → Optional[ExecutionResult]` | QA score < 8 시 Self-Refine 재실행 (최대 3회) |

### adapters

| 어댑터 | 설명 |
|--------|------|
| `CeleryAdapter` | Celery task 등록/dispatch/chord. `TaskQueuePort` 구현 |
| `SandboxExecutor` | gVisor/nsjail 코드 실행 샌드박스. `NodeExecutorPort` 부분 구현 |
| `LangGraphDispatcher` | REQ-004 AI 에이전트 노드 실행. `NodeExecutorPort` 부분 구현 |
| `ToolsetExecutor` | REQ-005 ExecuteToolUseCase 연동. `NodeExecutorPort` 부분 구현 |
| `SSEEventPublisher` | Redis Pub/Sub → SSE 스트림 상태 전파. `EventPublisherPort` 구현 |

## 의존 관계

```
Upstream (이 서비스가 의존):
  ├── common-schemas (REQ-012) → WorkflowSchema, ExecutionStatus, HandoffPayload 등
  ├── nodes-graph (REQ-003)    → GraphValidator (실행 전 재검증)
  ├── toolset (REQ-005)        → ExecuteToolUseCase (외부 도구 실행)
  ├── ai-agent (REQ-004)       → LangGraph 에이전트 노드 실행
  ├── auth (REQ-002)           → CredentialStore (자격증명 복호화)
  └── storage (REQ-008)        → WorkflowRepository, ExecutionRepository

Downstream (이 서비스에 의존):
  ├── api-server (REQ-009)     → Celery task dispatch
  └── ai-agent (REQ-004)       → HandoffPayload를 통한 핸드오프 수신
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `REDIS_URL` | Y | Celery broker + result backend |
| `DB_HOST` | Y | PostgreSQL 호스트 |
| `DB_PORT` | N | PostgreSQL 포트 (기본: 5432) |
| `DB_USER` | Y | DB 사용자명 |
| `DB_PASSWORD` | Y | DB 비밀번호 |
| `DB_NAME` | Y | DB 이름 |
| `CELERY_CONCURRENCY` | N | 워커 동시성 (기본: 4) |
| `NODE_EXECUTION_TIMEOUT` | N | 노드 실행 타임아웃 (기본: 300s) |

## Celery 큐 아키텍처

| 큐 | 라우팅 | 용도 | 동시성 |
|----|--------|------|--------|
| `default` | `category != "ai","external"` | 일반 노드 (DB 조회, 데이터 처리) | 4 |
| `llm` | `category == "ai"` | LLM 추론 노드 (Gemma4) | 2 |
| `external_api` | `category == "external"` | 외부 API 호출 (Google, Slack) | 4 |

## 재시도 정책

| 항목 | 기준 |
|------|------|
| 최대 재시도 | 3회 |
| 백오프 | 지수 (1s → 2s → 4s) |
| Retryable | 네트워크 타임아웃, 외부 API 5xx, Rate Limit |
| Non-retryable | 인증 실패, 스키마 불일치, 권한 부족 |

## 비기능 제약

| 항목 | 기준 |
|------|------|
| 일반 노드 실행 P95 | < 3초 |
| 멱등성 키 | execution_id + node_instance_id |
| 동시 워크플로우 | < 50 |
| Cold start | < 10초 (Celery worker) |

## 테스트

```bash
pytest services/execution-engine/tests/
```
