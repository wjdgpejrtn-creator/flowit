# ai_agent

> REQ-004: LangGraph 기반 13-노드 AI 에이전트, 워크플로우 자동 생성
>
> 구현 명세 → [`docs/specs/REQ-004-ai_agent.md`](../../docs/specs/REQ-004-ai_agent.md)

## 설치

```bash
pip install -e modules/ai_agent
pip install -e "modules/ai_agent[dev]"
```

## Quick Start

```python
from ai_agent.domain.services import (
    IntentAnalyzerService, DrafterService, QAEvaluatorService, SlotFillingService,
)
from common_schemas import MemoryEntry  # Sprint 3 SSOT — common_schemas로 이관
from ai_agent.domain.entities import ConversationMessage, SkillNode
from ai_agent.domain.value_objects import TurnLimit, QualityThreshold
from ai_agent.domain.ports import LLMPort, AgentMemoryRepository, WorkflowRepository, NodeRegistry
from ai_agent.application.agents.workflow_composer import (
    ComposeWorkflowUseCase, ContinueConversationUseCase,
)
from ai_agent.application.agents.personalization import SaveMemoryUseCase
# Sprint 3: 멀티 에이전트 구조로 전환됨. orchestrator/workflow_composer/skills_builder/personalization
# 각 sub-agent는 별도 Modal app으로 배포. 상세: docs/specs/plan/sprint-3.md
```

## common_schemas에서 import하는 타입

| 클래스 | import 경로 | 용도 |
|--------|-------------|------|
| `AgentState` | `common_schemas.agent` | LangGraph StateGraph state 타입 (`personal_memory: list[MemoryEntry]` 포함) |
| `DraftSpec` | `common_schemas.agent` | Consultant 초안 사양 |
| `IntentResult` | `common_schemas.agent` | IntentAnalyzerService 출력. `intent: IntentType` (clarify/draft/refine/propose/build_skill — `from common_schemas import IntentType`) |
| `SlotFillingState` | `common_schemas.agent` | 슬롯 채움 상태 |
| `MemoryEntry` | `common_schemas.agent` | Orchestrator ↔ sub-agent payload + RDB SSOT (Sprint 3 §2.4 이관) |
| `AgentProtocolRequest` / `AgentProtocolResponse` | `common_schemas.agent_protocol` | Inter-agent HTTP 통신 계약 |
| `WorkflowSchema` | `common_schemas.workflow` | 워크플로우 전체 스키마 |
| `NodeInstance` | `common_schemas.workflow` | 워크플로우 내 노드 인스턴스 |
| `NodeConfig` | `common_schemas.workflow` | 노드 정의/설정 |
| `Edge`, `Position` | `common_schemas.workflow` | 노드 연결, 캔버스 좌표 |
| `HandoffPayload` | `common_schemas.handoff` | REQ-007 전달 페이로드 |
| `EvaluationResult` | `common_schemas.handoff` | QA 평가 결과 (score, pass_flag, reason, feedback) |
| `AgentMode` | `common_schemas.enums` | 에이전트 모드 Enum (Sprint 3 `SKILL_BUILDER` 추가) |
| `ExecutionStatus` | `common_schemas.enums` | 실행 상태 Enum |
| `SSEFrame` | `common_schemas.transport` | 스트리밍 프레임 |

## Public API

### domain/entities

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `MemoryEntry` (re-export) | `entry_id: UUID`, `user_id: UUID`, `memory_type: Literal["preference","correction","workflow_pattern","summary"]`, `content: str`, `source_session_id: Optional[UUID]`, `metadata: dict[str, Any]`, `created_at: datetime` | `common_schemas.MemoryEntry`의 SSOT 재노출 — 신규 코드는 `from common_schemas import MemoryEntry` 사용 |
| `ConversationMessage` | `role: Literal["user","assistant","system"]`, `content: str`, `timestamp: datetime`, `metadata: Optional[dict]` | 대화 메시지 (AgentState.messages 항목) |

### domain/value_objects

| 클래스 | 설명 |
|--------|------|
| `TurnLimit` | 턴 상한 캡슐화. `MAX = 25`, `validate()` 초과 시 예외 |
| `QualityThreshold` | QA 통과 기준값. `MIN_SCORE = 8.0`, `is_pass(score: float) → bool` |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `IntentAnalyzerService` | `analyze(messages: list, context: dict) → IntentResult` | 사용자 발화 의도 분석 + importance_score 연산. `LLMPort` 의존 |
| `DrafterService` | `draft(spec: DraftSpec, candidates: list[NodeConfig]) → WorkflowSchema` | 워크플로우 초안 생성. `LLMPort` 의존 |
| `QAEvaluatorService` | `evaluate(workflow: WorkflowSchema, spec: DraftSpec) → EvaluationResult` | LLM-as-a-Judge 품질 평가 (score >= 8 통과). `LLMPort` 의존 |
| `SlotFillingService` | `next_question(state: SlotFillingState, spec: DraftSpec) → Optional[str]` | 슬롯 채움 로직 (순수 로직, 의존성 없음) |

### domain/ports (인터페이스)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `LLMPort` | `generate(prompt: str, **kwargs) → str` | `ai_agent/adapters/llm/` (ModalLLMAdapter) |
| | `generate_structured(prompt: str, schema: type[T]) → T` | |
| `AgentMemoryRepository` | `save(entry: MemoryEntry) → None` | `storage/repositories/` |
| | `find_by_user(user_id: UUID, limit: int) → list[MemoryEntry]` | |
| | `find_by_session(session_id: UUID, limit: int) → list[MemoryEntry]` | |
| `WorkflowRepository` | `save(workflow: WorkflowSchema) → UUID` | `storage/repositories/` |
| | `find_by_id(workflow_id: UUID) → Optional[WorkflowSchema]` | |
| `NodeRegistry` | `search(query: str, limit: int) → list[NodeConfig]` | `ai_agent/adapters/node_registry.py` (Facade) |
| | `get_schema(node_id: UUID) → NodeConfig` | |

### application/agents (Sprint 3 멀티 에이전트)

각 sub-agent는 별도 Modal app으로 배포되며 sub-agent 간 직접 import는 금지. 상세: `docs/specs/REQ-004-ai-agent.md` §2.2.

#### orchestrator/ (Main Orchestrator — 신정혜)

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `RouteRequestUseCase` | `user_id: UUID, session_id: UUID, message: str → AsyncGenerator[SSEFrame]` | LangGraph supervisor — personal_memory 로드 → intent 분류 → sub-agent HTTP 라우팅 → 결과 통합 |

#### workflow_composer/ (Workflow Composer — 신정혜)

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ComposeWorkflowUseCase` | `user_id: UUID, session_id: UUID, message: str → AsyncGenerator[SSEFrame]` | 13-노드 LangGraph 상태머신 실행 (턴 제한 ≤25, 스트리밍) |
| `ContinueConversationUseCase` | `session_id: UUID, message: str → AsyncGenerator[SSEFrame]` | 기존 세션 대화 이어가기 |

#### skills_builder/ (Skills Builder — 박아름)

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `BuildFromSOPUseCase` | `user_id: UUID, document: DocumentBlock → AsyncGenerator[SSEFrame]` | SOP 문서 → SkillNode 추출 → `NodeDefinitionRepository.upsert()` |
| `BuildFromIndustryDefaultUseCase` | `user_id: UUID, industry_code: str → AsyncGenerator[SSEFrame]` | 산업 seed (5종) → NodeDefinition 카탈로그 등록 |

#### personalization/ (Personalization — 햄햄/이가원)

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `LoadUserMemoryUseCase` | `user_id: UUID → list[MemoryEntry]` | GCS `MEMORY.md` + 관련 .md 파일 로드 |
| `UpdateUserMemoryUseCase` | `user_id: UUID, turn_count: int, session_summary: str\|None, workflow: WorkflowSchema\|None → bool` | 워크플로우 완료 후 LLM 패턴 추출 → .md 갱신. debounce 5분 (claim-first CAS) |
| `RecallPersonalSkillsUseCase` | `user_id: UUID, query: str, limit: int → list[PersonalSkill]` | BGE-M3 코사인 유사도 top-k |
| `SaveMemoryUseCase` | `session_id: UUID, entries: list[MemoryEntry] → None` | 대화 종료 후 RDB 메모리 저장 (`AgentMemoryRepository`) |

### adapters

| 어댑터 | 설명 |
|--------|------|
| `ModalLLMAdapter` | Modal L4 GPU 기반 LLM 호출 (Gemma 4). `LLMPort` 구현 |
| `ModalEmbeddingAdapter` | Modal BGE-M3 임베딩 호출. `nodes_graph.EmbedderPort` 구현 (SSOT: REQ-003 PR #30) |
| `HTTPSubAgentClient` | sub-agent VPC 내부 HTTP SSE 호출. `SubAgentClient` 구현 |
| `NodeRegistryAdapter` | `nodes_graph`의 `NodeDefinitionRepository`를 감싸는 Facade. `NodeRegistry` 구현 |
| `LangGraphOrchestrator` | LangGraph StateGraph 기반 내부 오케스트레이션 (13노드). 내부용, Port 아님 |
| `GCSMemoryStore` | GCS `gs://workflow-automation-personal/users/{user_id}/` 읽기/쓰기. `claim_debounce_window()`로 `.debounce.json` blob을 `if_generation_match` CAS 선점 (debounce 5분). `PersonalMemoryStore` 구현 |

## 의존 관계

```
Upstream (이 모듈이 의존):
  ├── common_schemas (REQ-012)
  │     └── AgentState, DraftSpec, IntentResult, WorkflowSchema, NodeConfig, HandoffPayload 등
  ├── auth (REQ-002)
  │     └── CredentialInjectionService
  └── nodes_graph (REQ-003)
        └── NodeDefinitionRepository, GraphValidator

Downstream (이 모듈에 의존):
  ├── api_server (REQ-009)        → ComposeWorkflowUseCase 호출
  ├── storage (REQ-008)           → AgentMemoryRepository, WorkflowRepository 구현체 제공
  └── execution_engine (REQ-007)  → HandoffPayload를 통해 workflow_id 전달 (간접)
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `MODAL_TOKEN_ID` | Y | Modal GPU 서비스 인증 ID |
| `MODAL_TOKEN_SECRET` | Y | Modal GPU 서비스 인증 시크릿 |
| `LLM_BASE_URL` | Y | Gemma 4 Modal endpoint URL |
| `EMBEDDING_BASE_URL` | Y | BGE-M3 임베딩 Modal endpoint URL |
| `SKILLS_BUILDER_URL` | Y | Skills Builder sub-agent Modal endpoint URL |
| `LLM_MODEL_NAME` | N | 사용 모델명 (기본: gemma-4) |
| `AGENT_MAX_TURNS` | N | 최대 턴 수 (기본: 25) |
| `QA_PASS_THRESHOLD` | N | QA 통과 점수 (기본: 8) |

## 아키텍처 제약

- LangGraph는 `adapters/langgraph/`에만 존재 (프레임워크는 어댑터 레이어)
- 비즈니스 로직은 `domain/services/`의 순수 함수로 구현
- ChromaDB 사용 금지 — 모든 RAG 검색은 pgvector 단일화
- 외부 LLM (OpenAI / Anthropic) 사용 금지 — 자체 호스팅 Gemma 4만 사용

## 비기능 제약

| 항목 | 기준 |
|------|------|
| Gemma 4 추론 P95 (256 토큰) | < 8초 (Modal L4) |
| QA Evaluator 통과 점수 | >= 8/10 |
| Prompt Injection 차단율 | >= 95% (10종 패턴) |
| Modal cold start | < 60초 |
| 최대 턴 수 | 25턴 (초과 시 압축) |

## 테스트

```bash
pytest modules/ai_agent/tests/
```
