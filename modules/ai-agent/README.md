# ai-agent

> REQ-004: LangGraph 기반 13-노드 AI 에이전트, 워크플로우 자동 생성

## 설치

```bash
pip install -e modules/ai-agent
pip install -e "modules/ai-agent[dev]"
```

## Quick Start

```python
from ai_agent.application.use_cases import ComposeWorkflowUseCase, OnboardingUseCase
from ai_agent.domain.services import IntentAnalyzerService, QAEvaluatorService, DrafterService
from ai_agent.domain.ports import AgentMemoryRepository, NodeRegistry, LLMPort
from ai_agent.domain.entities import MemoryEntry
```

## Public API

### domain/entities

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `MemoryEntry` | user_id, memory_type, content, source_session_id | 에이전트 기억 엔트리 |
| `CorrectionPattern` | — | 자기 교정 패턴 |

### domain/value_objects

| 클래스 | 주요 필드 | 설명 |
|--------|----------|------|
| `EvaluationResult` | score, pass_flag, reason, feedback | QA 평가 결과 (score ≥ 8 통과) |

### domain/services

| 서비스 | 메서드 | 설명 |
|--------|--------|------|
| `IntentAnalyzerService` | `analyze_intent(messages) → IntentResult` | 사용자 의도 분석 (clarify/draft/refine/propose) |
| `QAEvaluatorService` | `evaluate(workflow) → EvaluationResult` | LLM-as-a-Judge 품질 평가 |
| `DrafterService` | `draft_workflow(intent, nodes) → WorkflowSchema` | 워크플로우 초안 생성 |
| `OnboardingConsultant` | — | Skills Wizard 온보딩 세션 관리 |
| `SecurityGuard` | `check(input) → pass/block` | Prompt Injection 10종 패턴 차단, 입력 길이 2000자 제한 |
| `MemorySummarizer` | `summarize(session) → MemoryEntry[]` | 세션 종료 시 비동기 장기 기억 생성 |

### domain/ports (인터페이스)

| 포트 (ABC) | 메서드 | 구현 위치 |
|------------|--------|----------|
| `AgentMemoryRepository` | save, search(user_id, query, k), delete | `storage/repositories/` |
| `NodeRegistry` | `search(query, k) → list[NodeConfig]`, `get_schema(node_type) → dict` | 퍼사드 — `nodes-graph` 래핑 |
| `LLMPort` | `generate(messages, tools) → response`, `embed(text) → vector` | `ai-agent/adapters/llm/` (자체 구현) |

### application/use_cases

| 유스케이스 | Input → Output | 설명 |
|-----------|----------------|------|
| `ComposeWorkflowUseCase` | `message, PermissionSource → AgentState` | 13-노드 LangGraph 상태머신 실행 (턴 제한: ≤25) |
| `OnboardingUseCase` | — | Skills Wizard 온보딩 세션 |

### adapters/langgraph — LangGraph 상태머신 (13 노드)

| 노드 | 호출 대상 | 역할 |
|------|----------|------|
| `security_node` | CredentialInjectionService (REQ-002) | 리스크 평가 + 권한 검증 |
| `onboarding_node` | OnboardingConsultant | 온보딩 흐름 |
| `intent_node` | IntentAnalyzerService | 의도 분류 |
| `retriever_node` | NodeRegistry | 노드 후보 검색 |
| `drafter_node` | DrafterService | 초안 생성 |
| `validator_node` | GraphValidator (REQ-003) | 그래프 검증 (최대 3회 반복) |
| `qa_evaluator_node` | QAEvaluatorService | 품질 평가 (score ≥ 8) |
| `propose_node` | — | 제안 준비 |
| `promote_node` | — | 최종 확정 |

### adapters/llm

| 어댑터 | 설명 |
|--------|------|
| `ModalAdapter` | Modal L4 GPU 기반 LLM 호출 (Gemma 4 + BGE-M3 임베딩) |

## 의존 관계

```
이 모듈 → common-schemas (AgentState, WorkflowSchema, NodeConfig, PermissionSource, SSEFrame 등)
이 모듈 → auth (CredentialInjectionService)
이 모듈 → nodes-graph (GraphValidator, NodeDefinitionRepository → NodeRegistry 퍼사드)
이 모듈 ← api-server (POST /api/v1/ai/compose 라우터에서 호출)
이 모듈 ← storage (AgentMemoryRepository 구현)
```

## 환경 변수

| 변수명 | 필수 | 설명 |
|--------|------|------|
| `MODAL_TOKEN_ID` | Y | Modal GPU 서비스 인증 ID |
| `MODAL_TOKEN_SECRET` | Y | Modal GPU 서비스 인증 시크릿 |
| `LLM_MODEL_NAME` | N | 사용 모델명 (기본: gemma-4) |
| `AGENT_MAX_TURNS` | N | 최대 턴 수 (기본: 25) |
| `QA_PASS_THRESHOLD` | N | QA 통과 점수 (기본: 8) |

## 아키텍처 제약

- LangGraph는 `adapters/langgraph/`에만 존재 (프레임워크는 어댑터 레이어)
- 비즈니스 로직은 `domain/services/`의 순수 함수로 구현
- Checkpointer 스레드 ID: `f"{user_id}:{session_id}"`
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

## AI Negative (금지 사항)

- Gemma 4 평가 컨텍스트 / chat_messages / agent_memories에 credential 원본값 포함 금지
- 3회 초과 실패 시 자동으로 낮은 기준 통과 처리 금지
- 일회성 잡담을 agent_memories에 저장 금지

## 테스트

```bash
pytest modules/ai-agent/tests/
```
