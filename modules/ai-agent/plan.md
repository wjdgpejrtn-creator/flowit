# REQ-004 ai-agent 구현 계획

- **담당자**: 신정혜
- **브랜치**: `feature/req-004-ai-agent`
- **작성일**: 2026-05-07
- **기준 문서**: `docs/specs/REQ-004-ai-agent.md`

---

## 0. 사전 확인 사항 (코딩 전 필수)

### common-schemas에서 import할 타입 (자체 정의 금지)

| 타입 | 위치 | 비고 |
|------|------|------|
| `AgentState` | `common_schemas.agent` | messages, draft_spec, intent_result 등 |
| `DraftSpec` | `common_schemas.agent` | natural_language_intent, slot_filling_state 등 |
| `SlotFillingState` | `common_schemas.agent` | asked, pending, filled |
| `IntentResult` | `common_schemas.agent` | intent (clarify/draft/refine/propose), confidence, analyzed_entities |
| `EvaluationResult` | `common_schemas.handoff` | score, pass_flag, reason, feedback — **value_objects에 재정의 금지** |
| `WorkflowSchema` | `common_schemas.workflow` | |
| `NodeConfig` | `common_schemas.workflow` | |
| `SSEFrame` 계열 | `common_schemas.transport` | SessionFrame, AgentNodeFrame, ResultFrame, SlotFillQuestionFrame |

### 사용 가능한 외부 모듈 (development에 머지 완료)

| 모듈 | import 경로 | 사용 목적 |
|------|------------|---------|
| `CredentialInjectionService` | `auth.domain.services` | security_node 리스크 평가 |
| `GraphValidator` | `nodes_graph.domain.services` | 그래프 검증 |
| `NodeDefinitionRepository` (ABC) | `nodes_graph.domain.ports` | NodeRegistry 내부 참조 |

---

## 1. 구현 대상

### 1-1. domain/entities/ ✅ 완료

| 파일 | 클래스 | 상태 |
|------|--------|------|
| `memory_entry.py` | `MemoryEntry` | ✅ `source_session_id: Optional[UUID] = None`, `metadata: dict`, `is_ephemeral()` |
| `conversation_message.py` | `ConversationMessage` | ✅ `role: Literal["user","assistant","system"]`, `timestamp`, `metadata` |

### 1-2. domain/value_objects/ ✅ 완료

| 파일 | 클래스 | 상태 |
|------|--------|------|
| `turn_limit.py` | `TurnLimit` | ✅ `MAX=25`, `validate(count)`, `is_exceeded(count)` |
| `quality_threshold.py` | `QualityThreshold` | ✅ `MIN_SCORE=8.0`, `is_pass(score)` |

### 1-3. domain/ports/ ✅ 완료

| 파일 | 클래스 | 메서드 | 상태 |
|------|--------|--------|------|
| `llm_port.py` | `LLMPort` | `generate(prompt: str, **kwargs) → str`, `generate_structured(prompt, schema: type[T]) → T` | ✅ |
| `agent_memory_repository.py` | `AgentMemoryRepository` | `save(entry) → None`, `find_by_user(user_id, limit=20) → list[MemoryEntry]` | ✅ |
| `node_registry.py` | `NodeRegistry` | `search(query, k=10) → list[NodeConfig]` | ✅ |
| `workflow_repository.py` | `WorkflowRepository` | `save(workflow) → UUID`, `find_by_id(workflow_id) → Optional[WorkflowSchema]` | ✅ |

### 1-4. domain/services/ ✅ 완료

| 파일 | 클래스 | 시그니처 | 상태 |
|------|--------|---------|------|
| `security_guard.py` | `SecurityGuard` | `validate(text, permission) → None` — 10종 패턴 차단, 2000자 제한 | ✅ |
| `intent_analyzer.py` | `IntentAnalyzerService` | `analyze(messages: list, context: dict) → IntentResult` | ✅ |
| `drafter.py` | `DrafterService` | `draft(spec: DraftSpec, candidates: list[NodeConfig]) → WorkflowSchema` | ✅ |
| `qa_evaluator.py` | `QAEvaluatorService` | `evaluate(workflow: WorkflowSchema, spec: DraftSpec) → EvaluationResult` | ✅ |
| `slot_filling_service.py` | `SlotFillingService` | `next_question(state, spec) → Optional[str]`, `is_complete(state) → bool` — LLM 없는 순수 도메인 | ✅ |

### 1-5. application/use_cases/ ✅ 완료

| 파일 | 클래스 | Input → Output | 상태 |
|------|--------|----------------|------|
| `compose_workflow.py` | `ComposeWorkflowUseCase` | `execute(user_id, session_id, message) → AsyncGenerator[SSEFrame, None]` — QA retry 최대 3회 | ✅ |
| `continue_conversation.py` | `ContinueConversationUseCase` | `execute(session_id, user_id, message) → AsyncGenerator[SSEFrame, None]` | ✅ |
| `save_memory.py` | `SaveMemoryUseCase` | `execute(session_id, entries) → None` — ephemeral 항목 건너뜀 | ✅ |

### 1-6. adapters/llm/ ⏳ 미구현

| 파일 | 클래스 | 설명 |
|------|--------|------|
| `modal_adapter.py` | `ModalLLMAdapter` | LLMPort 구현체 — Modal L4 GPU (Gemma 4 + BGE-M3) |

### 1-7. adapters/langgraph/ ⏳ 미구현

| 파일/폴더 | 설명 |
|------|------|
| `nodes/security_node.py` | SecurityGuard + CredentialInjectionService |
| `nodes/intent_node.py` | IntentAnalyzerService |
| `nodes/retriever_node.py` | NodeRegistry |
| `nodes/drafter_node.py` | DrafterService |
| `nodes/qa_evaluator_node.py` | QAEvaluatorService |
| `nodes/promote_node.py` | WorkflowRepository.save |
| `nodes/slot_filling_node.py` | SlotFillingService |
| `nodes/error_node.py` | 오류 처리 |
| `graph_builder.py` | StateGraph 빌드 — 노드 연결, 조건부 엣지 |
| `orchestrator.py` | LangGraph 실행 진입점 |

---

## 2. 구현 순서 (TDD: Red → Green → Refactor)

```
Phase 1  domain/entities/          ✅ 완료 (39 tests passing)
Phase 2  domain/value_objects/     ✅ 완료
Phase 3  domain/ports/             ✅ 완료
Phase 4  domain/services/          ✅ 완료
Phase 5  application/use_cases/    ✅ 완료
Phase 6  adapters/llm/             ⏳ Modal 연동 구현 예정
Phase 7  adapters/langgraph/       ⏳ LangGraph 노드 구현 예정
```

---

## 3. SSE 스트리밍 출력 계약

`ComposeWorkflowUseCase.execute()` 가 yield하는 프레임 순서:

```
SessionFrame(session_id=..., user_id=...)
AgentNodeFrame(agent_node_name="intent_node")
  [intent == "clarify"] → SlotFillQuestionFrame(question=...) → return
  [intent == "draft"]   →
    AgentNodeFrame("retriever_node")
    [for attempt in range(3)]:
      AgentNodeFrame("drafter_node")
      AgentNodeFrame("qa_evaluator_node")
      [qa pass] → break
    AgentNodeFrame("promote_node")
    ResultFrame(intent="draft", payload={"workflow_id": "..."})
```

---

## 4. 아키텍처 제약 (위반 시 CI 실패)

| 금지 사항 | 이유 |
|----------|------|
| `domain/`에서 LangGraph import | 프레임워크는 adapters에만 |
| `AgentState`, `EvaluationResult` 자체 재정의 | common-schemas SSOT 위반 |
| `OnboardingConsultant` (LLM 의존 슬롯 필링) | `SlotFillingService` (순수 도메인)로 대체됨 |
| LLMPort에 messages list 전달 | `generate(prompt: str)` — 단일 문자열만 |
| OpenAI / Anthropic LLM 직접 사용 | Gemma 4 (Modal) 전용 |
| ChromaDB 사용 | pgvector 단일화 |
| QA 3회 실패 시 기준 완화 자동 통과 | QA 무결성 위반 |
| agent_memories에 credential 원본값 저장 | 보안 규칙 위반 |

---

## 4. 비기능 요구사항

| 항목 | 기준 |
|------|------|
| Gemma 4 추론 P95 (256 토큰) | < 8초 |
| QA Evaluator 통과 점수 | ≥ 8/10 (`QualityThreshold.MIN_SCORE`) |
| Prompt Injection 차단율 | ≥ 95% (10종 패턴) |
| Modal cold start | < 60초 |
| 최대 턴 수 | 25턴 (`TurnLimit.MAX`) |

---

## 5. 팀 액션 아이템 (조장 황대원에게 전달)

| 이슈 | 내용 |
|------|------|
| H-5 | 클래스 다이어그램 `.drawio` 원본 파일 제출 필요 (현재 PNG만 있음) |
| M-7 | `Chunk.importance_score` 계산 시점·로직을 REQ-006 김진형과 합의 후 architecture.md에 반영 |
| M-2 | AgentState는 common-schemas를 사용함으로 확정 — 별도 이슈 없음 |

---

## 6. 환경 변수

```
MODAL_TOKEN_ID      (필수)
MODAL_TOKEN_SECRET  (필수)
LLM_MODEL_NAME      (기본: gemma-4)
AGENT_MAX_TURNS     (기본: 25)
QA_PASS_THRESHOLD   (기본: 8)
```
