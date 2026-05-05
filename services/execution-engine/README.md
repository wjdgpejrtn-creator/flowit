# execution-engine

> REQ-007: Celery 워커, LangGraph StateGraph + TopologicalScheduler 실행, 에이전트 디스패처

## 설치

```bash
pip install -e services/execution-engine
pip install -e "services/execution-engine[dev]"
```

## 실행

```bash
# Celery 워커 시작
celery -A src.main worker --loglevel=info --concurrency=4

# Beat 스케줄러 (주기적 작업)
celery -A src.main beat --loglevel=info
```

## Quick Start

```python
# Celery task로 워크플로우 실행 트리거
from execution_engine.src.application.use_cases import ExecuteWorkflowUseCase

# api-server에서 호출:
execute_workflow.delay(workflow_id="...", execution_context={...})
```

## Public API

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `TopologicalScheduler` | `schedule(workflow: WorkflowSchema) → list[list[NodeInstance]]` | 위상 정렬(Kahn's) → 병렬 실행 레벨 계산 |

### domain/ports (인터페이스)

| 포트 (ABC) | 메서드 | 설명 |
|------------|--------|------|
| `WorkflowRepositoryPort` | `get(workflow_id) → WorkflowSchema` | 워크플로우 조회 |
| `NodeExecutorPort` | `execute(node: NodeInstance, inputs: dict) → dict` | 개별 노드 실행 |
| `TaskQueuePort` | `dispatch(task_name, args) → task_id` | Celery 태스크 발행 |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ExecuteWorkflowUseCase` | `workflow_id, context → ExecutionResult` | 전체 워크플로우 오케스트레이션 |
| `DispatchNodeUseCase` | `NodeInstance, inputs → NodeResult` | 단일 노드 실행 디스패치 |

### adapters

| 어댑터 | 설명 |
|--------|------|
| `CeleryAdapter` | Celery task 등록 및 실행 |
| `SandboxExecutor` | 보안 샌드박스 내 코드 실행 |
| `LangGraphDispatcher` | AI 에이전트 노드 실행 (REQ-004 연동) |

## 레이어 구조

```
src/
├── domain/
│   ├── services/        ← TopologicalScheduler (위상 정렬)
│   └── ports/           ← 추상 인터페이스
├── application/
│   └── use_cases/       ← ExecuteWorkflow, DispatchNode
├── adapters/            ← Celery, Sandbox, LangGraph
└── dependencies/        ← 워커 DI 컨테이너
```

```
실행 흐름:
  Celery Task 수신
    → ExecuteWorkflowUseCase
    → TopologicalScheduler.schedule() (위상 정렬 → 레벨별 정렬)
    → Level 1 노드 병렬 실행
        → ExecuteToolUseCase (REQ-005) 또는 LangGraphDispatcher (REQ-004)
    → Level 2 노드 병렬 실행 ...
    → ExecutionRepository에 결과 저장
    → SSE로 프론트엔드에 상태 전파
```

## 의존 관계

```
이 서비스 → common-schemas (WorkflowSchema, ExecutionStatus, HandoffPayload)
이 서비스 → nodes-graph (GraphValidator — 실행 전 재검증)
이 서비스 → toolset (ExecuteToolUseCase — 외부 도구 실행)
이 서비스 → ai-agent (LangGraph 에이전트 노드 실행)
이 서비스 → storage (WorkflowRepository, ExecutionRepository)
이 서비스 ← api-server (Celery task dispatch로 호출)
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

## 노드 실행 생명주기

```
pending → running → succeeded
                  → failed (retryable → retrying → running)
                  → failed (non-retryable → 즉시 종료)
                  → cancelled
```

## 재시도 정책

| 항목 | 기준 |
|------|------|
| 최대 재시도 | 3회 |
| 백오프 | 지수 (1s → 2s → 4s) |
| Retryable 에러 | 네트워크 타임아웃, 외부 API 5xx, Rate Limit |
| Non-retryable | 인증 실패, 스키마 불일치, 권한 부족 |

## Celery 큐 아키텍처

| 큐 | 용도 | 동시성 |
|----|------|--------|
| `default` | 일반 노드 (DB 조회, 데이터 처리) | 4 |
| `llm` | LLM 추론 노드 (Gemma4 호출) | 2 |
| `external_api` | 외부 API 호출 (Google, Slack) | 4 |

## 실행 모드

| 모드 | 대상 | 전송 방식 |
|------|------|----------|
| `serverless` | Celery Worker (Cloud Run) | Redis broker 태스크 큐잉 |
| `agent` | 고객 VPC Agent | WebSocket push (RSA 재암호화) |

## 병렬 실행

- 같은 레벨의 노드: Celery chord로 병렬 실행 → 모든 완료 시 다음 레벨
- 실패 정책: `fail_fast` (하나 실패 시 전체 중단) / `continue` (나머지 계속)
- QA Evaluator 연동: score < 8 → 워크플로우 재디스패치 (최대 3회 Self-Refine)

## Pause/Resume

- 사용자 승인 노드(HITL)에서 일시 중지
- 24시간 TTL — 초과 시 자동 cancelled
- `POST /api/v1/executions/{id}/resume`으로 재개

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
