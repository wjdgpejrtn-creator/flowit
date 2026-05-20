# common_schemas (REQ-012)

Pydantic v2 기반 공유 스키마 패키지. Python SSOT에서 TypeScript 인터페이스를 자동 생성한다.

## 구조

```
packages/common_schemas/
├── python/
│   ├── common_schemas/   # Pydantic v2 모델 (58 symbols)
│   ├── tests/            # pytest 단위테스트
│   └── pyproject.toml
├── typescript/
│   └── src/generated/    # codegen 산출물 (index.ts)
└── scripts/
    └── generate_ts.py    # Python → TypeScript codegen
```

## 설치

```bash
# 모노레포 루트에서
pip install -e packages/common_schemas/python

# 개발 의존성 포함
pip install -e "packages/common_schemas/python[dev]"
```

## Quick Start

```python
from common_schemas import (
    WorkflowSchema, NodeInstance, Edge, Position,
    NodeConfig, NodeContext,
    AgentState, DraftSpec, IntentResult, SlotFillingState, UnresolvedNode,
    DocumentBlock, ContentBlock, FileMeta, SourceRef, BBox, ParserMeta, SheetMeta,
    AnalysisResult,
    PermissionSource, PlaintextCredential,
    HandoffPayload, EvaluationResult,
    SkillDocument,
)
from common_schemas.enums import AgentMode, ExecutionStatus, RiskLevel, ErrorCode, IntentType
from common_schemas.exceptions import DomainError, ValidationError, NotFoundError
from common_schemas.transport import (
    SSEFrame, SessionFrame, AgentNodeFrame, RationaleDeltaFrame,
    SlotFillQuestionFrame, DraftSpecDeltaFrame, ResultFrame, ErrorFrame, AnySSEFrame,
    Message, ToolCall, LLMResponse,  # ADR-0015 §D4 LLM tool-use transport
)
```

## 모듈 구성

| 모듈 | 내용 |
|------|------|
| `workflow` | Position, Edge, NodeInstance, NodeConfig, NodeExecutionState, WorkflowSchema |
| `node` | NodeContext (노드 실행 컨텍스트, ADR-0018) |
| `agent` | AgentState, DraftSpec, IntentResult, SlotFillingState, UnresolvedNode |
| `document` | BBox, FileMeta, SourceRef, ParserMeta, SheetMeta, ContentBlock, DocumentBlock, AnalysisResult |
| `security` | PermissionSource, PlaintextCredential |
| `transport` | SSE frame 타입(`transport/sse.py`) + LLM tool-use 타입(`transport/llm.py`, ADR-0015 §D4) |
| `handoff` | HandoffPayload, EvaluationResult |
| `skill_document` | SkillDocument (스킬 지침서 SKILL.md, ADR-0017) |
| `enums` | AgentMode, ExecutionStatus, RiskLevel, ErrorCode, IntentType |
| `exceptions` | DomainError 계층 (Validation, Authorization, NotFound, Conflict, Integrity) |
| `validation` | ValidationErrorItem, ValidationErrorResponse |

## Public API

### workflow.py — 워크플로우 정의

| 클래스 | 설명 |
|--------|------|
| `WorkflowSchema` | 워크플로우 전체 정의 (nodes, edges, metadata) |
| `NodeInstance` | 워크플로우 내 노드 인스턴스 (position, config, credential_id) |
| `NodeConfig` | 노드 카탈로그 정의 (node_type, input/output_schema, risk_level) |
| `NodeExecutionState` | 노드 실행 상태 (status, attempt, last_error) |
| `Edge` | 노드 간 연결 (source → target, 조건부 분기 포함) |
| `Position` | 캔버스 좌표 VO (x, y) |

### node.py — 노드 실행 컨텍스트

| 클래스 | 설명 |
|--------|------|
| `NodeContext` | 노드 1회 실행분 컨텍스트 (execution_id, user_id, connection_token) — ADR-0018, `BaseNode.process(input, context)` 전달용 |

### agent.py — AI 에이전트 상태

| 클래스 | 설명 |
|--------|------|
| `AgentState` | LangGraph 상태 컨테이너 (messages, draft, intent, mode) |
| `DraftSpec` | 워크플로우 초안 명세 |
| `IntentResult` | 의도 분석 결과 (`intent: IntentType` — clarify/draft/refine/propose/build_skill) |
| `SlotFillingState` | 온보딩 슬롯 채움 상태 |
| `UnresolvedNode` | 미확정 노드 참조 |

### document.py — 문서 파싱 결과

| 클래스 | 설명 |
|--------|------|
| `DocumentBlock` | 파싱된 문서 최상위 컨테이너 |
| `ContentBlock` | 개별 콘텐츠 블록 (text, table, image, heading, code) |
| `FileMeta` | 원본 파일 메타데이터 |
| `SourceRef` | 원본 위치 참조 VO (page, section, bbox) |
| `BBox` | OCR/레이아웃 바운딩 박스 (x1, y1, x2, y2) |
| `ParserMeta` | 파서 이름, 버전, 실행시간 메타 |
| `SheetMeta` | Excel 시트 메타 (sheet_name, row_count, col_count) |
| `AnalysisResult` | AI 분석 결과 (요약, 핵심 포인트) |

### security.py — 보안 모델

| 클래스 | 설명 |
|--------|------|
| `PermissionSource` | 사용자 권한 컨텍스트 (user_id, role, department_id, risk_ceiling) |
| `PlaintextCredential` | 복호화된 자격증명 (자동 wipe 지원) |

### transport/sse.py — SSE 스트리밍 프레임

| 클래스 | 설명 |
|--------|------|
| `SSEFrame` | 기본 SSE 프레임 (frame_type 필드) |
| `SessionFrame` | 세션 초기화 (session_id, langgraph_thread_id) |
| `AgentNodeFrame` | 현재 실행 에이전트 노드 |
| `RationaleDeltaFrame` | AI 추론 실시간 스트리밍 |
| `SlotFillQuestionFrame` | 사용자 질문 프레임 |
| `DraftSpecDeltaFrame` | 초안 증분 업데이트 |
| `ResultFrame` | 최종 결과 (intent: clarify/draft/refine/propose) |
| `ErrorFrame` | 에러 알림 |
| `PipelineStatusFrame` | 생성 파이프라인 서비스별 진행 상태 (`service_name`, `status`, `elapsed_ms`) — 오른쪽 사이드바 |
| `IntentResultFrame` | 의도 분석 결과 (`intent`, `entities`) — 오른쪽 사이드바 |
| `QAMetricFrame` | QA 평가 결과 (`score`, `attempt`, `pass_flag`, `feedback`) — 오른쪽 사이드바 |
| `WorkflowDraftFrame` | 워크플로우 초안 (`nodes`, `connections`) — 가운데 캔버스 실시간 시각화 |
| `AnySSEFrame` | Discriminated union — frame_type 기반 역직렬화 (13종) |

### transport/llm.py — LLM tool-use transport (ADR-0015 §D4)

| 클래스 | 설명 |
|--------|------|
| `Message` | LLM 대화 메시지 (`role`, `content`, `tool_call_id`, `name`) — system/user/assistant/tool 4종 role |
| `ToolCall` | LLM이 요청한 도구 호출 (`id`, `name`, `arguments`) — LLM 응답 직렬화용 |
| `LLMResponse` | LLM 응답 (`content`, `tool_calls`, `finish_reason`) — `LLMPort.generate()` 반환 타입 (F2 신정혜 PR-A 이후) |

### handoff.py — 에이전트 → 실행엔진 핸드오프

| 클래스 | 설명 |
|--------|------|
| `HandoffPayload` | REQ-004 → REQ-007 전달 페이로드 |
| `EvaluationResult` | QA 평가 결과 (score, pass_flag, reason) |

### skill_document.py — 스킬 지침서

| 클래스 | 설명 |
|--------|------|
| `SkillDocument` | 스킬 SKILL.md 지침서 (skill_id, name, description, instructions, scripts, templates) — ADR-0017 이중 저장의 "지침서" 측. 생산자 ai_agent / 저장자 skills_marketplace |

### enums.py — 공유 열거형

| Enum | 값 |
|------|-----|
| `AgentMode` | ONBOARDING, WIZARD, EDIT, GENERAL, SECURITY, SKILL_BUILDER |
| `ExecutionStatus` | RUNNING, PAUSED, COMPLETED, FAILED |
| `RiskLevel` | Low, Medium, High, Restricted |
| `ErrorCode` | 도메인 에러 코드 열거 |
| `IntentType` | CLARIFY, DRAFT, REFINE, PROPOSE, BUILD_SKILL (IntentResult.intent SSOT) |

### exceptions.py — 도메인 예외 계층

| 예외 | 용도 |
|------|------|
| `DomainError` | 기본 클래스 (code: ErrorCode, message: str) |
| `ValidationError` | 데이터 검증 실패 |
| `AuthorizationError` | 권한 부족 |
| `NotFoundError` | 리소스 미존재 |
| `ConflictError` | 상태 충돌 |
| `IntegrityError` | 데이터 무결성 위반 |

### validation.py — 검증 에러 리포팅

| 클래스 | 설명 |
|--------|------|
| `ValidationErrorResponse` | 배치 에러 응답 (errors, is_valid) |
| `ValidationErrorItem` | 개별 검증 에러 (field, error_code, severity) |

## 사용 예시

### Python 서비스

```python
from common_schemas import WorkflowSchema, NodeInstance, Position, Edge
from common_schemas.enums import ExecutionStatus
from common_schemas.exceptions import ValidationError

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

from common_schemas.transport import AnySSEFrame

frame = AnySSEFrame.model_validate({"frame_type": "error", "code": "E_CYCLE_DETECTED", "message": "..."})
```

### TypeScript 프론트엔드

```typescript
import type { WorkflowSchema, AgentState, AnySSEFrame } from "@workflow-automation/common_schemas";

async function fetchWorkflow(id: string): Promise<WorkflowSchema> {
  const res = await fetch(`/api/workflows/${id}`);
  return res.json();
}

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

## 의존 관계

```
Upstream (이 패키지가 의존):
  └── pydantic >= 2.7.0 (유일한 외부 의존성)

Downstream (이 패키지에 의존):
  ├── modules/auth (REQ-002)
  ├── modules/nodes_graph (REQ-003)
  ├── modules/ai_agent (REQ-004)
  ├── modules/toolset (REQ-005)
  ├── modules/doc_parser (REQ-006)
  ├── modules/storage (REQ-008)
  ├── services/execution_engine (REQ-007)
  ├── services/api_server (REQ-009)
  └── services/frontend (REQ-010) — TypeScript 자동 생성 타입
```

## 설계 규칙

- 이 패키지는 **어떤 프레임워크도 import하지 않음** (FastAPI, SQLAlchemy, LangGraph 금지)
- 모든 모델은 `frozen=True` (PlaintextCredential, NodeContext 제외 — `wipe()` 지원)
- 모든 Enum은 `str`을 상속하여 JSON 직렬화 호환
- ID 필드는 `uuid.UUID` 타입
- Optional 필드는 명시적 `Optional[T] = None`
- 필드 타입 불일치 시 이 패키지의 정의가 우선 (SSOT 원칙)
- TypeScript 타입은 Python에서 단방향 생성 — 수동 편집 금지

## TypeScript Codegen

```bash
python packages/common_schemas/scripts/generate_ts.py
```

`typescript/src/generated/index.ts`가 재생성된다. 이 파일은 직접 편집하지 말 것.

## 테스트

```bash
pytest packages/common_schemas/python/tests -v
```
