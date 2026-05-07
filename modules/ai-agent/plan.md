# REQ-004 ai-agent 구현 계획

- **담당자**: 신정혜
- **브랜치**: `feature/req-004-ai-agent`
- **작성일**: 2026-05-07

---

## 0. 사전 확인 사항 (코딩 전 필수)

### common-schemas에서 import할 타입 (자체 정의 금지)

| 타입 | 위치 | 비고 |
|------|------|------|
| `AgentState` | `common_schemas.agent` | messages, draft_spec, intent_result, node_candidates, workflow_draft, mode, turn_count(≤25) |
| `DraftSpec` | `common_schemas.agent` | natural_language_intent, unresolved_nodes, slot_filling_state 등 |
| `IntentResult` | `common_schemas.agent` | intent (clarify/draft/refine/propose), confidence, analyzed_entities |
| `EvaluationResult` | `common_schemas.handoff` | score, pass_flag, reason, feedback — **value_objects에 재정의 금지** |
| `WorkflowSchema` | `common_schemas.workflow` | |
| `NodeConfig` | `common_schemas.workflow` | |
| `PermissionSource` | `common_schemas.security` | |
| `SSEFrame` 계열 | `common_schemas.transport` | AgentNodeFrame, ResultFrame 등 |

### 사용 가능한 외부 모듈 (development에 머지 완료)

| 모듈 | import 경로 | 사용 목적 |
|------|------------|---------|
| `CredentialInjectionService` | `auth.domain.services.credential_injection` | security_node 리스크 평가 |
| `GraphValidator` | `nodes_graph.domain.services.graph_validator` | validator_node 그래프 검증 |
| `NodeDefinitionRepository` (ABC) | `nodes_graph.domain.ports.node_definition_repository` | NodeRegistry 내부에서 참조 |

---

## 1. 구현 대상

### 1-1. domain/entities/ (자체 정의)

| 파일 | 클래스 | 주요 필드 |
|------|--------|----------|
| `memory_entry.py` | `MemoryEntry` | user_id: UUID, memory_type: str, content: str, source_session_id: UUID, created_at: datetime |
| `correction_pattern.py` | `CorrectionPattern` | pattern_id: UUID, user_id: UUID, original: str, corrected: str, frequency: int |

### 1-2. domain/value_objects/ (사용 안 함)

`EvaluationResult`는 `common_schemas.handoff`가 SSOT. 이 폴더에 새 VO를 정의하지 않는다.

### 1-3. domain/ports/ (ABC 정의)

| 파일 | 클래스 | 메서드 |
|------|--------|--------|
| `agent_memory_repository.py` | `AgentMemoryRepository` | `save(entry) → MemoryEntry`, `search(user_id, query, k) → list[MemoryEntry]`, `delete(entry_id)` |
| `node_registry.py` | `NodeRegistry` | `search(query, k) → list[NodeConfig]`, `get_schema(node_type) → dict` |
| `llm_port.py` | `LLMPort` | `generate(messages, tools) → response`, `embed(text) → list[float]` |

### 1-4. domain/services/ (핵심 비즈니스 로직)

| 파일 | 클래스 | 핵심 규칙 |
|------|--------|---------|
| `security_guard.py` | `SecurityGuard` | Prompt Injection 10종 패턴 차단, 입력 2000자 제한 |
| `intent_analyzer.py` | `IntentAnalyzerService` | `analyze_intent(messages) → IntentResult` — LLMPort를 통해 분류 |
| `drafter.py` | `DrafterService` | `draft_workflow(intent, nodes) → WorkflowSchema` — WorkflowSchema는 common-schemas SSOT |
| `qa_evaluator.py` | `QAEvaluatorService` | `evaluate(workflow) → EvaluationResult` — score ≥ 8 통과 |
| `onboarding_consultant.py` | `OnboardingConsultant` | Skills Wizard 세션 관리 |
| `memory_summarizer.py` | `MemorySummarizer` | `summarize(session) → list[MemoryEntry]` — 세션 종료 시 비동기 장기 기억 |

### 1-5. application/use_cases/

| 파일 | 클래스 | Input → Output |
|------|--------|----------------|
| `compose_workflow.py` | `ComposeWorkflowUseCase` | `(message: str, permission: PermissionSource) → AgentState` — 13-노드 LangGraph 실행 |
| `onboarding.py` | `OnboardingUseCase` | 온보딩 세션 생성/운영 |

### 1-6. adapters/llm/

| 파일 | 클래스 | 설명 |
|------|--------|------|
| `modal_adapter.py` | `ModalAdapter` | LLMPort 구현체 — Modal L4 GPU (Gemma 4 + BGE-M3) |

### 1-7. adapters/langgraph/nodes/ (13개)

| 노드 | 호출 대상 | 역할 |
|------|----------|------|
| `security_node.py` | `SecurityGuard`, `CredentialInjectionService` | 입력 검증 + 권한 리스크 평가 |
| `onboarding_node.py` | `OnboardingConsultant` | 온보딩 흐름 |
| `intent_node.py` | `IntentAnalyzerService` | 의도 분류 |
| `retriever_node.py` | `NodeRegistry` | 노드 후보 검색 |
| `drafter_node.py` | `DrafterService` | 워크플로우 초안 생성 |
| `validator_node.py` | `GraphValidator` | 그래프 검증 (최대 3회 반복) |
| `qa_evaluator_node.py` | `QAEvaluatorService` | 품질 평가 (score ≥ 8) |
| `propose_node.py` | — | 제안 준비 (SSE ResultFrame 전송) |
| `promote_node.py` | — | 최종 확정 |
| `clarify_node.py` | `LLMPort` | 추가 정보 요청 |
| `refine_node.py` | `DrafterService` | 워크플로우 수정 |
| `compress_node.py` | `MemorySummarizer` | 25턴 초과 시 컨텍스트 압축 |
| `error_node.py` | — | 오류 처리 및 HandoffPayload 생성 |

### 1-8. adapters/langgraph/

| 파일 | 설명 |
|------|------|
| `graph_builder.py` | StateGraph 빌드 — 13개 노드 연결, 조건부 엣지 |
| `checkpointer.py` | 스레드 ID: `f"{user_id}:{session_id}"` |

---

## 2. 구현 순서 (TDD: Red → Green → Refactor)

```
Phase 1  domain/entities/          ← 외부 의존 없음, 가장 먼저
Phase 2  domain/ports/             ← ABC만, 테스트 불필요
Phase 3  domain/services/          ← Port를 mock으로 단위 테스트
Phase 4  application/use_cases/    ← Port mock으로 단위 테스트
Phase 5  adapters/llm/             ← Modal 연동 통합 테스트
Phase 6  adapters/langgraph/       ← 전체 통합 테스트
```

---

## 3. 아키텍처 제약 (위반 시 CI 실패)

| 금지 사항 | 이유 |
|----------|------|
| `domain/`에서 LangGraph import | 프레임워크는 adapters에만 |
| `AgentState`, `EvaluationResult` 자체 재정의 | common-schemas SSOT 위반 |
| OpenAI / Anthropic LLM 사용 | Gemma 4 (Modal) 전용 |
| ChromaDB 사용 | pgvector 단일화 |
| 3회 초과 실패 시 자동 낮은 기준 통과 처리 | QA 무결성 위반 |
| agent_memories에 credential 원본값 저장 | 보안 규칙 위반 |

---

## 4. 비기능 요구사항

| 항목 | 기준 |
|------|------|
| Gemma 4 추론 P95 (256 토큰) | < 8초 |
| QA Evaluator 통과 점수 | ≥ 8/10 |
| Prompt Injection 차단율 | ≥ 95% (10종 패턴) |
| Modal cold start | < 60초 |
| 최대 턴 수 | 25턴 (초과 시 compress_node) |

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
