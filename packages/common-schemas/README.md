# common-schemas (REQ-012)

Pydantic v2 기반 공유 스키마 패키지. Python SSOT에서 TypeScript 인터페이스를 자동 생성한다.

## 구조

```
packages/common-schemas/
├── python/
│   ├── common_schemas/   # Pydantic v2 모델 (42 symbols)
│   ├── tests/            # pytest 단위테스트
│   └── pyproject.toml
├── typescript/
│   └── src/generated/    # codegen 산출물 (index.ts)
└── scripts/
    └── generate_ts.py    # Python → TypeScript codegen
```

## Python 설치

```bash
pip install -e packages/common-schemas/python[dev]
```

## 테스트

```bash
pytest packages/common-schemas/python/tests -v
```

## TypeScript Codegen

```bash
python packages/common-schemas/scripts/generate_ts.py
```

`typescript/src/generated/index.ts`가 재생성된다. 이 파일은 직접 편집하지 말 것.

## 모듈 구성

| 모듈 | 내용 |
|------|------|
| `enums` | AgentMode, ExecutionStatus, RiskLevel, ErrorCode |
| `exceptions` | DomainError 계층 (Validation, Authorization, Execution, NotFound) |
| `workflow` | Position, Edge, NodeInstance, NodeConfig, WorkflowSchema |
| `document` | BBox, FileMeta, ContentBlock, DocumentBlock, AnalysisResult 등 |
| `agent` | AgentState, DraftSpec, IntentResult, SlotFillingState |
| `transport` | SSE frame 타입 (Session, AgentNode, Error 등) + AnySSEFrame discriminated union |
| `validation` | ValidationErrorItem, ValidationErrorResponse |
| `security` | PermissionSource, PlaintextCredential |
| `handoff` | HandoffPayload, EvaluationResult |

## 사용 예시

### Python 서비스

```python
from common_schemas import WorkflowSchema, NodeInstance, Position, Edge
from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ValidationError

# 워크플로우 생성
workflow = WorkflowSchema(
    workflow_id="550e8400-e29b-41d4-a716-446655440000",
    name="My Workflow",
    scope="private",
    is_draft=True,
    nodes=[
        NodeInstance(
            instance_id="...",
            node_id="...",
            parameters={},
            position=Position(x=100, y=200),
        )
    ],
    connections=[],
)

# SSE 프레임 파싱
from common_schemas.transport import AnySSEFrame

frame = AnySSEFrame.model_validate({"frame_type": "error", "code": "E_CYCLE_DETECTED", "message": "..."})
```

### TypeScript 프론트엔드

```typescript
import type { WorkflowSchema, AgentState, AnySSEFrame } from "@workflow-automation/common-schemas";

// API 응답 타입 적용
async function fetchWorkflow(id: string): Promise<WorkflowSchema> {
  const res = await fetch(`/api/workflows/${id}`);
  return res.json();
}

// SSE 스트림 처리
function handleFrame(frame: AnySSEFrame) {
  switch (frame.frame_type) {
    case "error":
      console.error(frame.code, frame.message);
      break;
    case "rationale_delta":
      appendToUI(frame.delta);
      break;
  }
}
```

## 설계 원칙

- 모든 모델은 `frozen=True` (PlaintextCredential 제외 — `wipe()` 지원)
- ID 필드는 `uuid.UUID` 타입
- Optional 필드는 명시적 `Optional[T] = None`
- TypeScript 타입은 Python에서 단방향 생성 (SSOT)
