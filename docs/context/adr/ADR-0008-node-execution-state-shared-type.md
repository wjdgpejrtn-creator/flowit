# ADR-0008: NodeExecutionState를 common_schemas 공유 타입으로 도입

- **Status**: Accepted
- **Date**: 2026-05-07
- **Deciders**: @dhwang0803-glitch
- **Tags**: area/common_schemas, area/storage, area/execution_engine

## Context

REQ-007(execution_engine)과 REQ-008(storage) 간에 노드 실행 상태를 주고받는 계약이 필요했다.

- `ExecutionRepository.update_node_state()`는 개별 노드의 실행 상태(status, attempt, last_error)를 저장해야 한다.
- REQ-008 spec에는 `update_node_state(execution_id, node_id, state)` 시그니처가 정의되어 있으나, `state`의 타입이 명시되지 않았다.
- 이 상태 객체는 execution_engine이 생성하고 storage가 소비하므로, 두 모듈 모두 접근 가능한 위치에 타입이 정의되어야 한다.

## Decision

**`NodeExecutionState`를 `packages/common_schemas/python/common_schemas/workflow.py`에 Pydantic frozen model로 정의한다.**

```python
class NodeExecutionState(BaseModel):
    model_config = ConfigDict(frozen=True)
    node_instance_id: UUID
    status: Literal["pending", "running", "succeeded", "failed", "retrying", "cancelled"]
    attempt: int = 0
    last_error: Optional[str] = None
```

- `common_schemas.__init__`에서 export하여 `from common_schemas import NodeExecutionState`로 사용 가능
- `status` 필드는 Literal 타입으로 허용 값을 명시적으로 제한 (Enum 대신 Literal 선택 — 이유: 이 상태 값은 JSONB 저장 시 문자열로 직렬화되며, 다른 Enum과 달리 확장 가능성이 낮음)

## Consequences

### Positive
- execution_engine과 storage 간 노드 상태 계약이 타입 수준에서 보장됨
- frozen model이므로 실행 중 상태 객체의 불변성 유지
- `attempt`, `last_error` 포함으로 재시도 이력 추적 가능

### Negative / Trade-offs
- common_schemas에 실행 관련 타입이 추가되어 패키지 범위가 넓어짐
- status 값 변경 시 common_schemas 릴리즈 필요

### Follow-ups
- execution_engine(REQ-007) 구현 시 `NodeExecutionState` 생성 로직 작성
- storage `PgExecutionRepository.update_node_state()`는 이미 이 타입을 수용하도록 구현 완료 (PR #23)

## Alternatives Considered

- **Option A: flat 파라미터 유지** (`status: str, attempt: int, error: str`)
  기각 사유: 타입 안전성 없음, 호출부마다 파라미터 순서/이름 불일치 위험, 향후 필드 추가 시 시그니처 파편화

- **Option B: execution_engine 모듈 내부에 타입 정의**
  기각 사유: storage가 execution_engine을 import해야 하므로 의존성 방향 위반 (Persistence → Domain 역방향)

## References

- PR #23: `feat(storage): REQ-008 Storage 모듈 전체 구현`
- `packages/common_schemas/python/common_schemas/workflow.py` (NodeExecutionState 정의)
- `modules/storage/repositories/pg_execution_repository.py` (소비 측 구현)
