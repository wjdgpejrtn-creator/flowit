# REQ-004 AI Agent — 구현 명세

> **담당**: 신정혜  
> **모듈 경로**: `modules/ai_agent/`  
> **기준 문서**: 클래스 다이어그램 교차분석 확정본 (2026-05-05)

---

## common_schemas에서 import할 클래스

아래 타입은 `packages/common_schemas`(REQ-012)에서 정의된 SSOT이다. **절대로 모듈 내 재정의 금지.**

| 클래스명 | 소스 모듈 | import 경로 | 용도 |
|----------|-----------|-------------|------|
| `AgentState` | `common_schemas.agent` | `from common_schemas import AgentState` | LangGraph StateGraph의 state 타입. session_id, user_id, messages, turn_count(≤25), mode, draft_spec, intent_result, node_candidates, workflow_draft, execution_status 포함 |
| `DraftSpec` | `common_schemas.agent` | `from common_schemas import DraftSpec` | Consultant 단계에서 수집한 초안 사양 (natural_language_intent, unresolved_nodes, slot_filling_state 등) |
| `IntentResult` | `common_schemas.agent` | `from common_schemas import IntentResult` | IntentAnalyzerService 출력. intent(clarify/draft/refine/propose), confidence, analyzed_entities |
| `SlotFillingState` | `common_schemas.agent` | `from common_schemas import SlotFillingState` | 슬롯 채움 상태 (asked, pending, filled) |
| `UnresolvedNode` | `common_schemas.agent` | `from common_schemas import UnresolvedNode` | 아직 확정되지 않은 노드 후보 (placeholder_id, hint, candidate_node_types) |
| `WorkflowSchema` | `common_schemas.workflow` | `from common_schemas import WorkflowSchema` | 확정된 워크플로우 전체 스키마. 기존 "WorkflowDraft" 클래스명이 이것으로 통합됨 |
| `NodeInstance` | `common_schemas.workflow` | `from common_schemas import NodeInstance` | 워크플로우 내 노드 인스턴스. 기존 "WorkflowNode" 삭제 후 이 타입 사용 |
| `NodeConfig` | `common_schemas.workflow` | `from common_schemas import NodeConfig` | 노드 정의/설정. 기존 "NodeDef" 클래스명이 NodeConfig으로 변경됨 |
| `Edge` | `common_schemas.workflow` | `from common_schemas import Edge` | 노드 간 연결 (from_instance_id, to_instance_id, handles) |
| `Position` | `common_schemas.workflow` | `from common_schemas import Position` | 캔버스 좌표 (x, y) |
| `AgentMode` | `common_schemas.enums` | `from common_schemas.enums import AgentMode` | 에이전트 모드 Enum (ONBOARDING, WIZARD, EDIT, GENERAL, SECURITY) |
| `ExecutionStatus` | `common_schemas.enums` | `from common_schemas.enums import ExecutionStatus` | 실행 상태 Enum (RUNNING, PAUSED, COMPLETED, FAILED) |
| `HandoffPayload` | `common_schemas.handoff` | `from common_schemas import HandoffPayload` | QA 통과 후 REQ-007로 전달하는 핸드오프 데이터 |
| `EvaluationResult` | `common_schemas.handoff` | `from common_schemas import EvaluationResult` | QAEvaluatorService의 평가 결과 (score, pass_flag, reason, feedback) |

---

## 이 모듈에서 구현할 클래스

### Domain Layer (`domain/`)

#### `domain/entities/`

| 클래스명 | 설명 | 주요 필드 |
|----------|------|-----------|
| `MemoryEntry` | 에이전트 대화 메모리 항목 | `user_id: UUID`, `memory_type: str`, `content: str`, `source_session_id: Optional[UUID]` (신규 추가), `metadata: dict[str, Any]`, `created_at: datetime` |
| `ConversationMessage` | 대화 메시지 (AgentState.messages 항목용) | `role: Literal["user", "assistant", "system"]`, `content: str`, `timestamp: datetime`, `metadata: Optional[dict]` |

#### `domain/value_objects/`

| 클래스명 | 설명 | 비고 |
|----------|------|------|
| `TurnLimit` | turn_count 상한(25) 캡슐화 | `MAX = 25`, `validate()` 메서드로 초과 시 예외 |
| `QualityThreshold` | QA 평가 통과 기준값 | `MIN_SCORE = 8.0`, `is_pass(score: float) -> bool` |

#### `domain/services/`

| 클래스명 | 설명 | 주요 메서드 | 의존성 |
|----------|------|-------------|--------|
| `IntentAnalyzerService` | 사용자 발화 의도 분석 + importance_score 연산 | `analyze(messages: list, context: dict) -> IntentResult` | `LLMPort` |
| `DrafterService` | 워크플로우 초안 생성 (DraftSpec → WorkflowSchema) | `draft(spec: DraftSpec, candidates: list[NodeConfig]) -> WorkflowSchema` | `LLMPort` |
| `QAEvaluatorService` | 워크플로우 품질 평가 (LLM-as-a-Judge) | `evaluate(workflow: WorkflowSchema, spec: DraftSpec) -> EvaluationResult` | `LLMPort` |
| `SlotFillingService` | 슬롯 채움 로직 (부족한 정보 질의) | `next_question(state: SlotFillingState, spec: DraftSpec) -> Optional[str]` | 없음 (순수 로직) |

> **QAEvaluatorService 역할 경계**: 이 서비스는 워크플로우 "초안 품질"을 LLM으로 평가한다 (score >= 8 통과). REQ-005의 `RuntimeValidator`(도구 실행 시점 I/O 스키마 검증)와는 역할이 완전히 다르다.

#### `domain/ports/`

| 포트(ABC) | 설명 | 주요 메서드 | Adapter 구현 위치 |
|-----------|------|-------------|-------------------|
| `LLMPort` | LLM 호출 추상 인터페이스 | `generate(prompt: str, **kwargs) -> str`, `generate_structured(prompt: str, schema: type[T]) -> T` | `adapters/llm/` (Modal GPU) |
| `AgentMemoryRepository` | 메모리 저장소 | `save(entry: MemoryEntry) -> None`, `find_by_user(user_id: UUID, limit: int) -> list[MemoryEntry]`, `find_by_session(session_id: UUID, limit: int) -> list[MemoryEntry]` | `modules/storage/repositories/` |
| `WorkflowRepository` | 워크플로우 저장소 | `save(workflow: WorkflowSchema) -> UUID`, `find_by_id(workflow_id: UUID) -> Optional[WorkflowSchema]` | `modules/storage/repositories/` |
| `NodeRegistry` | 노드 카탈로그 검색 퍼사드 | `search(query: str, limit: int) -> list[NodeConfig]`, `get_schema(node_id: UUID) -> NodeConfig` | `adapters/node_registry.py` |

> **NodeRegistry 구현 주의**: `NodeDefinitionRepository`(nodes_graph 모듈 Port)를 DI로 주입받는 Facade 패턴. `search`와 `get_schema`만 외부에 노출한다. 내부적으로 `NodeDefinitionRepository.find_by_category()`, `.get_by_id()` 등을 위임 호출한다.

---

### Application Layer (`application/`)

#### `application/use_cases/`

| 유스케이스 | 설명 | 입력 | 출력 | 호출하는 서비스/포트 |
|-----------|------|------|------|---------------------|
| `ComposeWorkflowUseCase` | 워크플로우 자동 생성 전체 흐름 (LangGraph 오케스트레이션) | `user_id: UUID`, `session_id: UUID`, `message: str` | `AsyncGenerator[SSEFrame]` (스트리밍) | `IntentAnalyzerService`, `DrafterService`, `QAEvaluatorService`, `NodeRegistry`, `WorkflowRepository` |
| `ContinueConversationUseCase` | 기존 세션 대화 이어가기 | `session_id: UUID`, `message: str` | `AsyncGenerator[SSEFrame]` | `AgentMemoryRepository`, `LLMPort` |
| `SaveMemoryUseCase` | 대화 종료 후 메모리 저장 | `session_id: UUID`, `entries: list[MemoryEntry]` | `None` | `AgentMemoryRepository` |

---

### Adapters Layer (`adapters/`)

| 어댑터 | 설명 | 구현하는 Port | 외부 의존성 |
|--------|------|---------------|-------------|
| `ModalLLMAdapter` | Modal GPU 서버 호출 (Gemma 4 + BGE-M3) | `LLMPort` | `modal`, `httpx` |
| `NodeRegistryAdapter` | nodes_graph의 `NodeDefinitionRepository`를 감싸는 Facade | `NodeRegistry` | `nodes_graph.domain.ports.NodeDefinitionRepository` (DI 주입) |
| `LangGraphOrchestrator` | LangGraph StateGraph 기반 내부 워크플로우 그래프 | (내부용, Port 아님) | `langgraph` |

#### LangGraph StateGraph 노드 구성

```
                    ┌─────────────────────────────────────────────────┐
                    │         LangGraph StateGraph (내부 전용)          │
                    │                                                   │
  AgentState ──►   │  security_node                                    │
                    │       │                                           │
                    │       ▼                                           │
                    │  intent_node (IntentAnalyzerService)              │
                    │       │                                           │
                    │       ├──► [clarify] → consultant_node            │
                    │       │                    │                      │
                    │       │                    ▼                      │
                    │       │              slot_fill_node               │
                    │       │                    │                      │
                    │       │                    ▼ (loop back)          │
                    │       │                                           │
                    │       ├──► [draft/refine] → retriever_node       │
                    │       │                         │                 │
                    │       │                         ▼                 │
                    │       │                   drafter_node            │
                    │       │                   (DrafterService)        │
                    │       │                         │                 │
                    │       │                         ▼                 │
                    │       │                   validator_node          │
                    │       │                   (GraphValidator 호출)    │
                    │       │                         │                 │
                    │       │                         ▼                 │
                    │       │                   qa_evaluator_node       │
                    │       │                   (QAEvaluatorService)    │
                    │       │                         │                 │
                    │       │              ┌──── score < 8 ────┐       │
                    │       │              │ (최대 3회 재시도)    │       │
                    │       │              └──► drafter_node ──┘       │
                    │       │                         │                 │
                    │       │                    score >= 8             │
                    │       │                         ▼                 │
                    │       └──► [propose] → promote_node              │
                    │                              │                    │
                    │                              ▼                    │
                    │                         handoff_node              │
                    │                    (WorkflowRepository.save)      │
                    │                              │                    │
                    │                              ▼                    │
                    │                     workflow_id → REQ-007          │
                    └─────────────────────────────────────────────────┘
```

> **주의**: 이 LangGraph StateGraph는 AI Agent 내부 "대화 오케스트레이션"용이다. REQ-007 실행 엔진의 "워크플로우 실행"과는 완전히 별개의 그래프이다.

---

### SkillAgent 구조 (노드 간 서비스 흐름)

```
ConsultantNode
    → IntentAnalyzerService (intent 분석 + importance_score)
        → DrafterNode (초안 생성)
            → QAEvaluatorService (LLM-as-a-Judge, score >= 8 통과)
                → ComposerNode (확정 + 핸드오프)
```

---

## 합의된 변경사항 (클래스 다이어그램 교차분석)

| 항목 | 변경 전 | 변경 후 | 사유 |
|------|---------|---------|------|
| AgentState 위치 | REQ-004 자체 정의 | REQ-012 common_schemas import | SSOT 원칙 — 여러 모듈에서 참조 가능해야 함 |
| WorkflowDraft | 별도 클래스 존재 | `WorkflowSchema`로 통합 (is_draft 필드로 구분) | 중복 제거, 단일 스키마로 draft/published 구분 |
| WorkflowNode | 별도 클래스 | 삭제 → `NodeInstance` import | common_schemas의 NodeInstance가 동일 역할 수행 |
| NodeDef | REQ-004 자체 정의 | `NodeConfig` (REQ-012) import | 클래스명 통일 |
| MemoryEntry.source_session_id | 없음 | `Optional[UUID]` 필드 추가 | 메모리 출처 추적 가능하도록 신규 추가 |
| NodeRegistry | 독립 서비스 | Facade 패턴 (NodeDefinitionRepository DI 주입) | Clean Architecture 의존성 방향 준수 |

---

## 의존성 관계

### 이 모듈이 import하는 대상

```python
# common_schemas (REQ-012) — 모든 공유 타입
from common_schemas import (
    AgentState, DraftSpec, IntentResult, SlotFillingState,
    UnresolvedNode, WorkflowSchema, NodeInstance, NodeConfig,
    Edge, Position, HandoffPayload, EvaluationResult,
)
from common_schemas.enums import AgentMode, ExecutionStatus
from common_schemas.exceptions import ValidationError, DomainError
from common_schemas.transport import SSEFrame, AgentNodeFrame, SessionFrame

# auth (REQ-002) — domain/services만 허용
from auth.domain.services import CredentialInjectionService

# nodes_graph (REQ-003) — domain/ports, domain/services만 허용
from nodes_graph.domain.ports import NodeDefinitionRepository
from nodes_graph.domain.services import GraphValidator
```

### 이 모듈의 Port를 구현하는 외부 모듈

| Port | 구현 모듈 |
|------|-----------|
| `AgentMemoryRepository` | `modules/storage/repositories/` |
| `WorkflowRepository` | `modules/storage/repositories/` |

### 이 모듈을 import하는 외부 모듈

| 소비자 | import 대상 |
|--------|-------------|
| `modules/storage/` | `ai_agent.domain.ports.AgentMemoryRepository` (구현을 위해) |
| `services/api_server/` | `ai_agent.application.use_cases.ComposeWorkflowUseCase` (DI 조립) |
| `services/execution_engine/` | (간접 — HandoffPayload를 통해 workflow_id 전달) |

---

## 테스트 전략

```
tests/
├── unit/
│   ├── domain/
│   │   ├── test_intent_analyzer_service.py    # LLMPort mock
│   │   ├── test_drafter_service.py            # LLMPort mock
│   │   ├── test_qa_evaluator_service.py       # LLMPort mock, score 경계값
│   │   ├── test_slot_filling_service.py       # 순수 로직, mock 불필요
│   │   └── test_memory_entry.py               # entity validation
│   └── application/
│       ├── test_compose_workflow_use_case.py           # 모든 Port mock
│       ├── test_continue_conversation_use_case.py      # AgentMemoryRepository, LLMPort mock
│       └── test_save_memory_use_case.py
└── integration/
    ├── test_langgraph_orchestrator.py         # 실제 StateGraph 흐름 (LLM은 mock)
    └── test_node_registry_adapter.py          # NodeDefinitionRepository mock
```

---

## 파일 배치 요약

```
modules/ai_agent/
├── __init__.py
├── domain/
│   ├── __init__.py
│   ├── entities/
│   │   ├── __init__.py
│   │   ├── memory_entry.py          # MemoryEntry
│   │   └── conversation_message.py  # ConversationMessage
│   ├── value_objects/
│   │   ├── __init__.py
│   │   ├── turn_limit.py            # TurnLimit
│   │   └── quality_threshold.py     # QualityThreshold
│   ├── services/
│   │   ├── __init__.py
│   │   ├── intent_analyzer_service.py
│   │   ├── drafter_service.py
│   │   ├── qa_evaluator_service.py
│   │   └── slot_filling_service.py
│   └── ports/
│       ├── __init__.py
│       ├── llm_port.py              # LLMPort ABC
│       ├── agent_memory_repository.py
│       ├── workflow_repository.py
│       └── node_registry.py         # NodeRegistry ABC
├── application/
│   ├── __init__.py
│   └── use_cases/
│       ├── __init__.py
│       ├── compose_workflow_use_case.py
│       ├── continue_conversation_use_case.py
│       └── save_memory_use_case.py
├── adapters/
│   ├── __init__.py
│   ├── llm/
│   │   ├── __init__.py
│   │   └── modal_llm_adapter.py     # ModalLLMAdapter
│   ├── node_registry_adapter.py     # NodeRegistryAdapter (Facade)
│   └── langgraph_orchestrator.py    # LangGraphOrchestrator
├── tests/
│   ├── unit/
│   │   ├── domain/
│   │   └── application/
│   └── integration/
└── README.md
```
