# REQ-004 AI Agent — 구현 명세 (멀티 에이전트 구조)

> **담당**: 신정혜(Orchestrator + Workflow Composer + LLM base) · 박아름(Skills Builder) · 햄햄/이가원(Personalization)
> **모듈 경로**: `modules/ai_agent/`
> **기준 문서**: 클래스 다이어그램 교차분석 확정본 (2026-05-05), Sprint 3 plan (2026-05-11) — `docs/specs/plan/sprint-3.md`

---

## 0. Sprint 3 멀티 에이전트 전환 개요

ai_agent 모듈은 Sprint 3에서 **단일 ComposeWorkflowUseCase** 구조를 폐기하고 **Main Orchestrator + 3 Sub-Agent** 구조로 재배치되었다. 각 sub-agent는 독립된 Modal app으로 배포되며, **VPC 내부 HTTP**로 통신한다 (옵션 2 + 옵션 C).

| 에이전트 | 역할 | 담당자 | Modal app |
|---------|------|--------|----------|
| **Main Orchestrator** | LangGraph supervisor, intent 분류 → sub-agent 라우팅, personal memory 로드/통합 | 신정혜 | `orchestrator` |
| **Workflow Composer** | 사용자 채팅 → 워크플로우 초안·완성 (기존 13-노드 그래프 흡수) | 신정혜 | `agent-composer` |
| **Skills Builder** | SOP 문서/산업 default → NodeDefinition 카탈로그 등록 | 박아름 | `agent-skills-builder` |
| **Personalization** | 사용자 패턴 추출 → `MEMORY.md` GCS 저장/로드/recall | 햄햄(이가원) | `agent-personalization` |
| (공통) LLM base | Gemma 4 inference + BGE-M3 embedding | 신정혜 | `llm-base` |

### 단일 모듈 / 다중 배포

`modules/ai_agent`는 **단일 Python 패키지**이지만 sub-agent별 Modal app에 각각 배포된다. sub-agent 간 직접 코드 import는 **금지** — 각 Modal app의 entrypoint(composition root)에서 해당 sub-agent의 use case만 조립하고, 다른 sub-agent를 부르려면 HTTP 어댑터(`adapters/agent_clients/`)를 거친다.

---

## 1. common_schemas에서 import할 클래스

아래 타입은 `packages/common_schemas`(REQ-012)에서 정의된 SSOT이다. **절대로 모듈 내 재정의 금지.**

| 클래스명 | 소스 모듈 | import 경로 | 용도 |
|----------|-----------|-------------|------|
| `AgentState` | `common_schemas.agent` | `from common_schemas import AgentState` | LangGraph StateGraph의 state 타입. session_id, user_id, messages, turn_count(≤25), mode, draft_spec, intent_result, node_candidates, workflow_draft, execution_status, **personal_memory** 포함 |
| `DraftSpec` | `common_schemas.agent` | `from common_schemas import DraftSpec` | Workflow Composer Consultant 단계 초안 사양 |
| `IntentResult` | `common_schemas.agent` | `from common_schemas import IntentResult` | IntentAnalyzerService 출력. `intent: IntentType` (clarify/draft/refine/propose/build_skill), confidence, analyzed_entities |
| `SlotFillingState` | `common_schemas.agent` | `from common_schemas import SlotFillingState` | 슬롯 채움 상태 (asked, pending, filled) |
| `UnresolvedNode` | `common_schemas.agent` | `from common_schemas import UnresolvedNode` | 아직 확정되지 않은 노드 후보 |
| `MemoryEntry` | `common_schemas.agent` | `from common_schemas import MemoryEntry` | Orchestrator ↔ sub-agent payload + RDB SSOT. Sprint 3에서 ai_agent → common_schemas로 이관 (ai_agent.domain.entities.memory_entry는 호환용 재노출) |
| `MemoryType` | `common_schemas.agent` | `from common_schemas import MemoryType` | `Literal["preference","correction","workflow_pattern","summary"]` 별칭 |
| `AgentProtocolRequest` / `AgentProtocolResponse` | `common_schemas.agent_protocol` | `from common_schemas import AgentProtocolRequest, AgentProtocolResponse` | Inter-agent HTTP 통신 계약 (Sprint 3 §2.4에서 합의 — 2026-05-12 구현 완료) |
| `WorkflowSchema` | `common_schemas.workflow` | `from common_schemas import WorkflowSchema` | 확정된 워크플로우 전체 스키마 |
| `NodeInstance` | `common_schemas.workflow` | `from common_schemas import NodeInstance` | 워크플로우 내 노드 인스턴스 |
| `NodeConfig` | `common_schemas.workflow` | `from common_schemas import NodeConfig` | 노드 정의/설정 |
| `Edge`, `Position` | `common_schemas.workflow` | `from common_schemas import Edge, Position` | 노드 연결, 캔버스 좌표 |
| `AgentMode` | `common_schemas.enums` | `from common_schemas.enums import AgentMode` | 에이전트 모드 Enum (ONBOARDING, WIZARD, EDIT, GENERAL, SECURITY, **SKILL_BUILDER**) — Sprint 3 `SKILL_BUILDER` 추가됨 |
| `IntentResult.intent` | `common_schemas.enums.IntentType` | `from common_schemas import IntentType` | `IntentType(str, Enum)` 5값 — CLARIFY / DRAFT / REFINE / PROPOSE / BUILD_SKILL. v0.4.0(2026-05-18)에서 Literal → Enum 격상 (StrEnum이라 기존 문자열 비교/입력 호환 유지) |
| `ExecutionStatus` | `common_schemas.enums` | `from common_schemas.enums import ExecutionStatus` | 실행 상태 Enum |
| `HandoffPayload` | `common_schemas.handoff` | `from common_schemas import HandoffPayload` | QA 통과 후 REQ-007로 전달 |
| `EvaluationResult` | `common_schemas.handoff` | `from common_schemas import EvaluationResult` | QA 평가 결과 |
| `DocumentBlock` | `common_schemas.document` | `from common_schemas import DocumentBlock` | Skills Builder가 doc_parser 산출물 소비 |
| `SSEFrame`, `AgentNodeFrame`, `SessionFrame`, `ResultFrame`, `SlotFillQuestionFrame`, `DraftSpecDeltaFrame` | `common_schemas.transport` | `from common_schemas.transport import ...` | 기존 스트리밍 프레임 |
| `PipelineStatusFrame`, `IntentResultFrame`, `QAMetricFrame`, `WorkflowDraftFrame` | `common_schemas.transport` | `from common_schemas.transport import ...` | 실시간 모니터링 SSE 프레임 4종 (2026-05-19 추가) — 오른쪽 사이드바(PipelineStatus/IntentResult/QAMetric) + 가운데 캔버스(WorkflowDraft) |

> **Sprint 3 신규 타입 (2026-05-12 구현 완료)**: `AgentProtocolRequest/Response`(신규 모듈 `common_schemas.agent_protocol`), `MemoryEntry` 이관(ai_agent → common_schemas.agent), `AgentMode.SKILL_BUILDER`, `IntentResult.intent`에 `"build_skill"`, `AgentState.personal_memory: list[MemoryEntry]`. PR — `feature/req-012-agent-protocol`.

---

## 2. 이 모듈에서 구현할 클래스

### 2.1 Domain Layer (`domain/`) — sub-agent 공통

도메인 레이어는 sub-agent 간 공유된다. Port와 Service는 어떤 sub-agent의 use case에서도 import 가능하다.

#### `domain/entities/`

| 클래스명 | 설명 | 주요 필드 |
|----------|------|-----------|
| `MemoryEntry` (re-export) | 에이전트 대화 메모리 항목 — Sprint 3 SSOT는 `common_schemas.MemoryEntry`. `modules/ai_agent/domain/entities/memory_entry.py`는 호환성을 위한 재노출 shim. | `entry_id: UUID`, `user_id: UUID`, `memory_type: Literal["preference","correction","workflow_pattern","summary"]`, `content: str`, `source_session_id: Optional[UUID]`, `metadata: dict[str, Any]`, `created_at: datetime`, `is_ephemeral() -> bool` |
| `ConversationMessage` | 대화 메시지 (AgentState.messages 항목용) | `role: Literal["user","assistant","system"]`, `content: str`, `timestamp: datetime`, `metadata: Optional[dict]` |
| `PersonalSkill` | Personalization이 추출한 사용자 패턴 (memory.md 본문) | `user_id: UUID`, `skill_type: Literal["user","feedback","project","reference"]`, `name: str`, `description: str`, `body: str`, `embedding: Optional[list[float]]` (BGE-M3 768d), `updated_at: datetime` |
| `SkillNode` | Skills Builder가 SOP/산업 default/직무 영역 default에서 추출한 노드 후보 | `source_type: Literal["sop","industry_default","functional_domain"]`, `source_id: str` (document_id / industry_code / domain_code), `name: str`, `description: str`, `inputs: dict`, `outputs: dict`, `risk_level: RiskLevel` |
| `SessionRef` 🆕 | 세션 인덱스 항목 — `GCSSessionFrameStore`가 사용자별 인덱스를 관리하는 데 사용 | `session_id: UUID`, `user_id: UUID`, `workflow_id: Optional[UUID]`, `created_at: UtcDatetime`, `message_preview: str` (최대 100자) |

#### `domain/value_objects/`

| 클래스명 | 설명 | 비고 |
|----------|------|------|
| `TurnLimit` | turn_count 상한(25) 캡슐화 | `MAX = 25`, `validate()` |
| `QualityThreshold` | QA 평가 통과 기준값 | `MIN_SCORE = 8.0`, `is_pass(score: float) -> bool` |

#### `domain/services/`

| 클래스명 | 설명 | 주요 메서드 | 의존성 |
|----------|------|-------------|--------|
| `IntentAnalyzerService` | 사용자 발화 의도 분석 (orchestrator의 라우팅 입력 + composer의 흐름 분기 양쪽 사용) | `analyze(messages: list, context: dict) -> IntentResult` | `LLMPort` |
| `DrafterService` | 워크플로우 초안 생성 (DraftSpec → WorkflowSchema) | `draft(spec: DraftSpec, candidates: list[NodeConfig]) -> WorkflowSchema` | `LLMPort` |
| `QAEvaluatorService` | 워크플로우 품질 평가 (LLM-as-a-Judge) | `evaluate(workflow: WorkflowSchema, spec: DraftSpec) -> EvaluationResult` | `LLMPort` |
| `SlotFillingService` | 슬롯 채움 로직 (부족한 정보 질의) | `next_question(state: SlotFillingState, spec: DraftSpec) -> Optional[str]` | 없음 (순수 로직) |
| `WorkflowLayoutService` | 워크플로우 캔버스 노드 좌표 자동 배치 — Kahn's algorithm으로 위상 레벨 계산 후 `NodeInstance.position(x, y)` 할당. `drafter_node` 산출 직후 호출 | `apply_layout(workflow: WorkflowSchema) -> WorkflowSchema` | 없음 (`WorkflowSchema`, `Edge`, `NodeInstance`, `Position` — common_schemas만 의존, 순수 로직) |
| `WorkflowDiffService` 🆕 | draft(AI 제안)와 final(사용자 승인) 워크플로우를 구조적으로 비교해 피드백 패턴을 추출한다. 사용자 승인 시점에 호출되며, 결과(`WorkflowDiff`)를 Personalization Agent에 이벤트로 전달한다 | `compute(draft: WorkflowSchema, final: WorkflowSchema) -> WorkflowDiff` | 없음 (`WorkflowSchema`, `NodeInstance` — common_schemas만 의존, 순수 로직) |

> **QAEvaluatorService 역할 경계**: 이 서비스는 워크플로우 "초안 품질"을 LLM으로 평가한다 (score >= 8 통과). REQ-005의 `RuntimeValidator`(도구 실행 시점 I/O 스키마 검증)와는 역할이 완전히 다르다.

#### `domain/ports/`

| 포트(ABC) | 설명 | 주요 메서드 | Adapter 구현 위치 | 사용 sub-agent |
|-----------|------|-------------|-------------------|--------------|
| `LLMPort` | LLM 호출 추상 인터페이스 | `generate(prompt: str, **kwargs) -> str`, `generate_structured(prompt: str, schema: type[T]) -> T` | `adapters/llm/` (Modal GPU) | 전체 |
| `EmbedderPort` (nodes_graph 소유, ai_agent에서 import) | 임베딩 호출 추상 인터페이스 (BGE-M3 768d). Port ABC는 `nodes_graph/domain/ports/`에 정의, 구현체만 ai_agent가 소유 (예외 패턴, PR #30 5/12 결정) | `embed(text: str) -> list[float]`, `embed_batch(texts: list[str]) -> list[list[float]]` | `ai_agent/adapters/llm/modal_embedding_adapter.py` | composer, personalization, skills_builder |
| `AgentMemoryRepository` | 메모리 저장소 (대화 turn 단위) | `save(entry: MemoryEntry) -> None`, `find_by_user(user_id, limit) -> list[MemoryEntry]`, `find_by_session(session_id, limit) -> list[MemoryEntry]` | `modules/storage/repositories/` | composer, orchestrator |
| `PersonalMemoryStore` 🆕 | 사용자별 memory 파일 저장소 (GCS, MemoryFile 기반) | `load_index(user_id) -> list[MemoryFileRef]`, `save_index(user_id, refs) -> None`, `load_file(user_id, filename) -> MemoryFile`, `save_file(user_id, file) -> None`, `delete_file(user_id, filename) -> None`, `load_embedding(user_id, name) -> list[float]\|None`, `save_embedding(user_id, name, embedding) -> None`, `cleanup(user_id) -> None` (캐시 해제, default no-op), `claim_debounce_window(user_id, now, window) -> bool` (LLM 호출 전 `.debounce.json` CAS 선점 — 패자 즉시 False) | `adapters/memory/gcs_memory_store.py` (ai_agent 자체 어댑터) | personalization |
| `WorkflowRepository` | 워크플로우 저장소 | `save(workflow: WorkflowSchema) -> UUID`, `find_by_id(workflow_id) -> Optional[WorkflowSchema]` | `modules/storage/repositories/` | composer |
| `NodeRegistry` | 노드 카탈로그 검색 퍼사드 | `search(query: str, limit: int) -> list[NodeConfig]`, `get_schema(node_id: UUID) -> NodeConfig` | `adapters/node_registry_adapter.py` (nodes_graph 퍼사드) | composer, skills_builder |
| `SessionFrameStore` 🆕 | 세션별 SSE 프레임 저장소 — 모니터링 히스토리 재생 용도 | `save_session(ref: SessionRef, frames: list[AnySSEFrame]) -> None`, `load_frames(session_id: UUID, user_id: UUID) -> list[AnySSEFrame]`, `list_sessions(user_id: UUID, limit: int) -> list[SessionRef]` | `adapters/memory/gcs_session_frame_store.py` (GCS, ai_agent 자체 어댑터) | composer |
| `WorkflowDraftStore` 🆕 | 사용자 승인 전까지 Composer가 생성한 draft(`WorkflowSchema`)를 session 단위로 임시 보관. 승인 시점에 `WorkflowDiffService`가 draft·final을 비교해 Personalization에 이벤트로 전달한다 | `save_draft(session_id: UUID, draft: WorkflowSchema) -> None`, `load_draft(session_id: UUID) -> WorkflowSchema \| None`, `delete_draft(session_id: UUID) -> None` | 구현 어댑터 미정 (in-memory 또는 GCS) | composer |
| `SubAgentClient` 🆕 (선택) | sub-agent HTTP 호출 추상 (orchestrator 전용) | `call(agent: Literal["composer","skills_builder","personalization"], req: AgentProtocolRequest) -> AsyncGenerator[AgentProtocolResponse]` | `adapters/agent_clients/` (httpx 기반) | orchestrator |

> **PersonalMemoryStore 소유권**: GCS는 ai_agent 모듈 자체 어댑터로 구현한다 (`storage` 모듈을 경유하지 않음). 이유 — Personalization은 PostgreSQL이 아닌 GCS 파일 기반이며, storage 모듈은 RDB Repository에 한정. CLAUDE.md "Port → Adapter 매핑" 표에 명시.

---

### 2.2 Application Layer — Sub-Agent별 Use Case

application/agents/ 하위로 sub-agent별 폴더가 분리된다. **다른 sub-agent의 use case를 import하는 것은 금지** (HTTP 클라이언트 사용).

#### `application/agents/orchestrator/` — Main Orchestrator (신정혜)

| 유스케이스 | 설명 | 입력 | 출력 | 호출하는 서비스/포트 |
|-----------|------|------|------|---------------------|
| `RouteRequestUseCase` | 세션 시작 → personal_memory 로드 → intent 분류 → sub-agent 라우팅 → SSE 통합 | `user_id: UUID`, `session_id: UUID`, `message: str` | `AsyncGenerator[SSEFrame]` | `IntentAnalyzerService`, `SubAgentClient`(HTTP), Personalization Agent(HTTP) |

LangGraph supervisor 패턴 — Orchestrator 내부에 별도 StateGraph가 존재하며, 각 노드는 sub-agent HTTP를 호출한다 (in-process import 아님).

#### `application/agents/workflow_composer/` — Workflow Composer (신정혜)

| 유스케이스 | 설명 | 입력 | 출력 | 호출하는 서비스/포트 |
|-----------|------|------|------|---------------------|
| `ComposeWorkflowUseCase` | 워크플로우 자동 생성 전체 흐름 (기존 13-노드 그래프 그대로) | `user_id: UUID`, `session_id: UUID`, `message: str`, `personal_memory: list[MemoryEntry]` | `AsyncGenerator[SSEFrame]` | `IntentAnalyzerService`, `DrafterService`, `QAEvaluatorService`, `SlotFillingService`, `NodeRegistry`, `WorkflowRepository` |
| `ContinueConversationUseCase` | 기존 세션 대화 이어가기 | `session_id: UUID`, `message: str` | `AsyncGenerator[SSEFrame]` | `AgentMemoryRepository`, `LLMPort` |

#### `application/agents/skills_builder/` — Skills Builder (박아름)

| 유스케이스 | 설명 | 입력 | 출력 | 호출하는 서비스/포트 |
|-----------|------|------|------|---------------------|
| `BuildFromSOPUseCase` | SOP 문서(DocumentBlock) → SkillNode 목록 → **`skills_marketplace` upsert (NodeDefinition 메타 + SkillDocument GCS 파일 이중 저장)** | `user_id: UUID`, `document: DocumentBlock`, `personal_memory: list[MemoryEntry] \| None = None` | `AsyncGenerator[SSEFrame]` | `LLMPort`, `EmbedderPort`, **`SkillRepository.upsert()`(skills_marketplace)**, **`SkillDocumentStore.save()`(GCS)** |
| `BuildFromIndustryDefaultUseCase` | 산업 코드 → seed JSON 로드 → **`skills_marketplace` 이중 저장** | `user_id: UUID`, `industry_code: str` | `AsyncGenerator[SSEFrame]` | `EmbedderPort`, `SkillRepository.upsert()`, `SkillDocumentStore.save()` |
| `BuildFromFunctionalDomainUseCase` | 직무 영역 코드 → seed JSON 로드 → **`skills_marketplace` 이중 저장** | `user_id: UUID`, `domain_code: str` | `AsyncGenerator[SSEFrame]` | `EmbedderPort`, `SkillRepository.upsert()`, `SkillDocumentStore.save()` |

Sprint 3 baseline 5종 (2026-05-12 조장 합의):
- **산업 1종**: `ecommerce` (활성) / 기존 5종(manufacturing/service/wholesale_retail/food/it) 비활성화 — seed 파일 보존, 호출 시 `E_INDUSTRY_DEACTIVATED`
- **직무 영역 5종**: `customer_support`, `it_ops`, `document_data`, `hr`, `marketing` — 모두 활성

seed 파일:
- 산업: `modules/ai_agent/seeds/industry_defaults/{code}.json`
- 직무 영역: `modules/ai_agent/seeds/functional_domain_defaults/{code}.json`

LLM 자유 생성 산업 default는 v2(Sprint 4+) 이연.

##### 산출물 형식 — 이중 저장 (2026-05-20 조장 확정, ADR-0017)

`skills_marketplace`는 사내 SkillsMP 역할 (Anthropic SkillsMP 표준 레퍼런스, 외부 공유 X). Skills Builder는 다음 두 가지를 동시에 생성:

| 산출물 | 형식 | 저장 위치 | 소비자 |
|--------|------|----------|--------|
| `NodeDefinition` (메타) | pydantic + JSON Schema (`input_schema`/`output_schema`) | `skills_marketplace` 테이블 (PostgreSQL) | `execution_engine` (워크플로우 노드 실행, JSON Schema 재사용) |
| `SkillDocument` (지침서) | markdown frontmatter(`name`/`description`) + body(`instructions`) | GCS 버킷 (별도 파일 저장) | Main Agent (사용자 대화 중 노드 탐색 + 옵션 제시) |

> **현 구현 단계 (PR #106 → #111 → #113 → #123)**: SOP/functional/industry use case는 `ResultFrame.payload["skill_documents"]`에 `common_schemas.SkillDocument`를 `model_dump(mode="json")`한 리스트를 담아 반환한다 (PR #123에서 dict → **type-safe 객체 전환 완료** — `SkillDocument` SSOT는 common_schemas, PR #111). 각 항목 = `{skill_id, name, description, instructions, scripts, templates}`. **`SkillDocument`는 node가 아닌 지침서라 `node_type` 없이 `skill_id`(=NodeDefinition.node_id)로 NodeDefinition과 연결**한다 (조장 PR #113 결정 — node 오인 호출 방지). `node_type`은 `payload["node_types"]`에 별도 유지. `SkillDocumentStore.save()` 직접 wiring(GCS adapter + skills_marketplace use case 경유)은 후속. functional/industry는 seed에 `instructions`가 있을 때만 수집(선택) — **seed instructions 채우기 전까지 일부 seed 스킬은 SkillDocument가 비어 있을 수 있다** (의도된 갭, 후속 seed 작업으로 해소).

**Composer 검색 흐름 (5/20 조장 확정)**:
1. 사용자 입력 → `IntentAnalyzerService`로 intent 파악
2. `Workflow Composer`가 노드 탐색 타이밍에 `skills_marketplace` 동시 탐색
3. 사용자 의도와 유사한 skill 후보를 옵션으로 제시
4. 사용자 선택 → 워크플로우 그래프에 노드 추가 (`execution_engine` JSON Schema 실행)

**`execution_engine` 호환**: `NodeDefinition`의 `input_schema`/`output_schema` 그대로 재사용 — 기존 워크플로우 실행 인프라 변경 0.

**의존 모듈 (PR-2d 신설 예정, 2026-05-25 주말)**:
- `modules/skills_marketplace/` — `SkillRepository` ABC + `PersonalSkill`/`TeamSkill`/`CompanySkill` 3계층 (ADR-0012 v3)
- `SkillDocumentStore` Port (GCS adapter, `ai_agent/adapters/skill_document/` 위치 후보)

#### `application/agents/personalization/` — Personalization (햄햄/이가원)

| 유스케이스 | 설명 | 입력 | 출력 | 호출하는 서비스/포트 |
|-----------|------|------|------|---------------------|
| `LoadUserMemoryUseCase` | 세션 시작 시 MEMORY.md + 관련 .md 로드 | `user_id: UUID` | `list[MemoryEntry]` (protocol 페이로드) | `PersonalMemoryStore.load_index()`, `load_file()` |
| `UpdateUserMemoryUseCase` | 워크플로우 완료 후 LLM이 패턴 추출 → 변경된 .md만 선택 저장. **debounce 5분**: LLM 호출 전 `claim_debounce_window()`로 `.debounce.json` CAS 선점 — 패자는 LLM 없이 즉시 bail (claim-first 패턴) | `user_id: UUID`, `turn_count: int`, `session_summary: str\|None`, `workflow: WorkflowSchema\|None` | `bool` (저장 여부) | `PersonalMemoryStore.claim_debounce_window()`, `load_index()`, `save_file()`, `save_index()`, `LLMPort` — `turn_count < 3` 또는 `workflow.nodes` 없으면 early return |
| `RecallPersonalSkillsUseCase` | Composer가 prompt 작성 시 호출 — 관련 memory 검색 | `user_id: UUID`, `query: str` | `list[MemoryFile]` | `PersonalMemoryStore.load_index()`, `load_file()`, `load_embedding()`, `EmbedderPort.embed()` (코사인 유사도 매칭, top_k는 생성자 인자) |
| `SaveMemoryUseCase` | 기존 turn 단위 메모리 저장 (RDB AgentMemoryRepository) | `session_id: UUID`, `entries: list[MemoryEntry]` | `None` | `AgentMemoryRepository` |

> **SaveMemoryUseCase 유지 사유**: RDB 기반 conversation turn 메모리는 Personalization의 GCS 패턴 추출과 별개 책임. Sprint 3에서는 두 유스케이스가 공존하며, Sprint 4에서 통합 여부 재평가.

---

### 2.3 Adapters Layer (`adapters/`)

| 어댑터 | 설명 | 구현하는 Port | 외부 의존성 | 사용 sub-agent |
|--------|------|---------------|-------------|--------------|
| `ModalLLMAdapter` | Modal GPU 서버 호출 (Gemma 4) | `LLMPort` | `httpx`, `modal` | 전체 |
| `ModalEmbeddingAdapter` 🆕 | Modal GPU 임베딩 호출 (BGE-M3) | `EmbedderPort` (nodes_graph 소유, 예외 패턴 — PR #30 5/12 결정) | `httpx` | composer, personalization, skills_builder |
| `GCSMemoryStore` 🆕 | GCS 버킷 `gs://workflow-automation-personal/users/{user_id}/` 읽기/쓰기 | `PersonalMemoryStore` | `google-cloud-storage` | personalization |
| `GCSSessionFrameStore` 🆕 | 세션별 SSE 프레임 전체를 GCS에 저장 (`sessions/{user_id}/{session_id}.json`) + 사용자별 인덱스 관리 (`sessions/{user_id}/index.json`, 최대 100건). 모니터링 히스토리 재생에 사용 | `SessionFrameStore` | `google-cloud-storage` (asyncio.to_thread 래핑) | composer |
| `NodeRegistryAdapter` | nodes_graph의 `NodeDefinitionRepository`를 감싸는 Facade | `NodeRegistry` | `nodes_graph.domain.ports.NodeDefinitionRepository` (DI 주입) | composer, skills_builder |
| `HTTPSubAgentClient` 🆕 | 다른 sub-agent Modal endpoint 호출 (VPC 내부) | `SubAgentClient` | `httpx` | orchestrator |
| `LangGraphOrchestrator` | Workflow Composer 내부 13-노드 StateGraph. 선택 의존성: `PermissionResolver`(권한 확인), `EmbedderPort`+`SearchSkillsUseCase`(커스텀 스킬 검색), `SessionFrameStore`(모니터링 세션 저장) | (내부용, Port 아님) | `langgraph` | composer |
| `LangGraphSupervisor` 🆕 | Main Orchestrator supervisor 그래프 | (내부용, Port 아님) | `langgraph` | orchestrator |

---

## 3. LangGraph 그래프 구성

### 3.1 Main Orchestrator Supervisor Graph (신규)

```
                ┌────────────────────────────────────────────────────────┐
                │  Main Orchestrator (modal app: orchestrator)            │
                │                                                          │
   사용자 메시지 ──►│  load_memory_node                                       │
                │       │  (HTTP → agent-personalization                    │
                │       │          : LoadUserMemoryUseCase)                  │
                │       ▼                                                    │
                │  intent_node (IntentAnalyzerService)                      │
                │       │                                                    │
                │       ├─ intent=draft/refine/clarify ─► composer_node      │
                │       │                                  (HTTP → agent-composer  │
                │       │                                   : ComposeWorkflowUseCase)│
                │       │                                                    │
                │       ├─ intent=build_skill ──────────► skills_node        │
                │       │                                  (HTTP → agent-skills-builder│
                │       │                                   : BuildFromSOP/Industry) │
                │       │                                                    │
                │       └─ intent=propose ──────────────► finalize_node      │
                │                                                            │
                │  update_memory_node (워크플로우 완료 후)                     │
                │       │  (HTTP → agent-personalization                     │
                │       │          : UpdateUserMemoryUseCase)                 │
                │       ▼                                                    │
                │  SSE 통합 yield                                             │
                └────────────────────────────────────────────────────────┘
```

### 3.2 Workflow Composer 내부 StateGraph (16-노드, 2026-05-21 확장)

```
AgentState ─► security_node ─► intent_node ─►
  ├─ [clarify] ─► consultant_node ─► slot_fill_node (loop back)
  ├─ [draft/refine] ─► retriever_node ─► drafter_node ─► validator_node ─► qa_evaluator_node
  │                                                       │
  │                                            score < 8 (최대 3회 retry)
  │                                            score >= 8
  │                                                       ▼
  └─ [propose] ─► promote_node ─► handoff_node (WorkflowRepository.save → saved_workflow_id)
                                              │
                                              ▼
                                        execute_node          ← 실행 엔진 호출 (REQ-007 연동)
                                              │
                                              ▼
                                        evaluate_output_node  ← LLM 산출물 퀄리티 검증
                                              │
                                              ▼
                                        user_confirm_node     ← 결과 사용자 제시
                                              │
                                              ▼
                                        memory_save → END
```

#### 신규 노드 상세 (2026-05-21 추가, PR #135)

| 노드 | 역할 | 구현 상태 |
|------|------|----------|
| `execute_node` | `POST /api/v1/workflows/{id}/execute` 호출 → execution_id 획득 → 결과 폴링 (`GET /api/v1/executions/{id}`, 3초 간격, 최대 5분) | ✅ 구현 완료 — `EXECUTION_ENGINE_URL` 환경변수 필요 (팀장님 Secret Manager 등록 대기) |
| `evaluate_output_node` | 실행 산출물 퀄리티 평가. LLMPort 주입 시 LLM 평가, 미주입 시 실행 상태 기반 휴리스틱 | ✅ 구현 완료 |
| `user_confirm_node` | `ResultFrame(intent="execution_review")` emit — 실행 결과 요약을 프론트엔드에 전달 | ✅ 구현 완료 |

#### `promote_node` 변경 (2026-05-21)

`promote_node`는 `is_draft=False` 설정 후 **`WorkflowDraftStore.save_draft(session_id, draft)`** 를 호출해 AI 생성 원본 초안을 임시 보관한다. 사용자 승인 시 `ApproveWorkflowUseCase`가 이 초안과 최종본을 비교해 `WorkflowDiff`를 생성한다 (§3.3 참조).

#### `validator_node` 변경 (2026-05-21)

`GraphValidator` 구조 검증에 더해, `PermissionResolver`가 주입된 경우 워크플로우 각 노드의 `risk_level`을 조회해 사용자 `permission.risk_ceiling` 초과 노드를 차단한다.

> **drafter_node 좌표 배치**: `drafter_node`는 `DrafterService.draft()` 호출 직후 `WorkflowLayoutService.apply_layout(workflow)`를 실행해 각 `NodeInstance`에 캔버스 x,y 좌표를 부여한다. 이 좌표는 프론트엔드 React Flow 캔버스에 직접 사용된다.

> **주의**: 두 그래프는 별개. Orchestrator supervisor는 sub-agent 라우팅용, Composer 내부 그래프는 워크플로우 생성용. REQ-007 실행 엔진의 "워크플로우 실행"과도 모두 별개.

---

### 3.3 사용자 승인 diff 흐름 (2026-05-21 햄햄 제안, 신정혜 구현)

**문제**: Composer가 생성한 draft는 `AgentState`에만 존재하고, 사용자가 승인/수정해 저장되는 final workflow는 `WorkflowRepository`에 별도 저장된다. 둘을 비교해 사용자 패턴을 학습하는 주체가 없었다.

**흐름**:

```
Composer → promote_node → draft WorkflowSchema 생성
                           ↓
             WorkflowDraftStore.save_draft(session_id, draft)   ← session에 임시 보관
                           ↓
사용자 승인 이벤트 수신 (프론트엔드 → api_server → Composer)
                           ↓
WorkflowDraftStore.load_draft(session_id) → draft
WorkflowRepository.find_by_id(workflow_id) → final
                           ↓
WorkflowDiffService.compute(draft, final) → WorkflowDiff
   • added_nodes: 사용자가 추가한 노드
   • removed_nodes: 사용자가 삭제한 노드
   • modified_params: 사용자가 수정한 파라미터
                           ↓
WorkflowDiff → Personalization Agent 이벤트 전달
(Personalization이 WorkflowDiff.to_feedback_lines()를 MemoryEntry로 변환, 햄햄 담당)
                           ↓
WorkflowDraftStore.delete_draft(session_id)  ← 정리
```

**담당 분리**:

| 역할 | 담당 |
|------|------|
| `WorkflowDiffService` 구현 (`domain/services/`) | 신정혜 ✅ |
| `WorkflowDraftStore` Port 정의 (`domain/ports/`) | 신정혜 ✅ |
| `WorkflowDraftStore` 어댑터 구현 (`InMemoryWorkflowDraftStore`) | 신정혜 ✅ (PR #135) |
| `ApproveWorkflowUseCase` — 승인 이벤트 수신 + diff 계산 + Personalization 이벤트 전달 | 신정혜 ✅ (PR #135) |
| `POST /v1/agent/approve` 엔드포인트 | 신정혜 ✅ (PR #135) |
| Personalization Agent — diff → MemoryEntry 변환 + 저장 | 햄햄(이가원) |

---

## 4. Inter-Agent 통신 계약

모든 sub-agent는 동일한 HTTP 프로토콜로 호출된다. 계약은 `packages/common_schemas/agent_protocol.py`(Sprint 3 §2.4에서 추가).

### 요청

```python
class AgentProtocolRequest(BaseModel):
    session_id: UUID
    user_id: UUID
    state: AgentState                # common_schemas
    personal_memory: list[MemoryEntry]
    payload: dict[str, Any]          # sub-agent별 추가 입력 (예: document)
    trace_id: Optional[str] = None   # OpenTelemetry 분산 추적
```

### 응답 (SSE 스트림)

```python
class AgentProtocolResponse(BaseModel):
    frames: list[SSEFrame]
    state_delta: dict
    next_action: Literal["continue", "complete", "error"]
```

### 엔드포인트 (각 Modal app)

- `POST /v1/agent/route` — `agent-composer`, `agent-skills-builder`, `agent-personalization` 동일
- `GET /v1/health` — health check (REST 표준 + 운영 도구 호환성, 2026-05-14 정정)

### SSE 종결 규칙

- 정상 종결: `complete` frame 1개만 발송
- 에러 종결: `error` frame → `complete` frame 순서로 발송 (dual 종결)

### 인증

VPC 내부 통신만 허용 (옵션 C). Modal app 외부 노출 금지. mTLS는 Sprint 4 이후.

---

## 5. Sub-Agent Modal 배포 단위

| Modal app | 담당자 | 사용 use case (해당 Modal app의 composition root에서 조립) |
|-----------|-------|--------------------------------------------------------|
| `llm-base` | 신정혜 | (모델 서빙, ai_agent Python 패키지 미포함) |
| `orchestrator` | 신정혜 | `RouteRequestUseCase` |
| `agent-composer` | 신정혜 | `ComposeWorkflowUseCase`, `ContinueConversationUseCase` |
| `agent-skills-builder` | 박아름 | `BuildFromSOPUseCase`, `BuildFromIndustryDefaultUseCase`, `BuildFromFunctionalDomainUseCase` |
| `agent-personalization` | 햄햄(이가원) | `LoadUserMemoryUseCase`, `UpdateUserMemoryUseCase`, `RecallPersonalSkillsUseCase`, `SaveMemoryUseCase` |

각 Modal app은 별도 composition root 모듈 (예: `services/agents/{name}/main.py` 또는 동등 위치)에서 필요한 Port 어댑터를 조립한다. 정확한 디렉토리 위치는 REQ-011(infra) 브랜치에서 확정. 멤버는 본인 app만 `modal deploy` 수행 — 타 멤버 영향 없음.

### 환경 변수 (sub-agent 공통 / 개별)

| 변수명 | 적용 범위 | 설명 |
|--------|----------|------|
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` | 전체 | Modal 인증 |
| `LLM_BASE_URL` | composer, orchestrator, skills_builder, personalization | `llm-base` Modal endpoint |
| `EMBEDDING_BASE_URL` | composer, personalization | BGE-M3 endpoint (보통 `llm-base`와 동일) |
| `ORCHESTRATOR_URL` | api_server | Orchestrator Modal endpoint |
| `COMPOSER_URL` / `SKILLS_BUILDER_URL` / `PERSONALIZATION_URL` | orchestrator | Sub-agent endpoint |
| `GCS_PERSONAL_BUCKET` | personalization | `workflow-automation-personal` |
| `GCS_SESSION_BUCKET` 🆕 | composer | SSE 세션 프레임 저장 버킷 (`GCSSessionFrameStore` 사용, Secret Manager key: `gcs-session-bucket`) |
| `EXECUTION_ENGINE_URL` 🆕 | composer | 실행 엔진 API base URL (Secret Manager key: `execution-engine-url`, PR #135) |
| `AGENT_MAX_TURNS` | composer | 25 |
| `QA_PASS_THRESHOLD` | composer | 8 |

---

## 6. Personalization — GCS `MEMORY.md` 패턴 (Claude Code 차용)

```
gs://workflow-automation-personal/users/{user_id}/
  MEMORY.md              # 인덱스 (- [Title](file.md) — one-line hook)
  user_role.md           # type: user
  workflow_patterns.md   # type: feedback
  favorite_nodes.md      # type: project
  integrations.md        # type: reference
```

각 .md 파일 frontmatter:

```markdown
---
name: {{memory name}}
description: {{one-line, used for relevance ranking}}
type: {{user|feedback|project|reference}}
updated_at: 2026-05-15T12:00:00+00:00   # UTC ISO-8601
embedding: [0.1, 0.2, ...]               # BGE-M3 768d (optional; P-2 이후 .emb.json으로 분리 예정)
---
{{body}}
```

`RecallPersonalSkillsUseCase`는 query 임베딩과 각 entry의 description 임베딩 코사인 유사도로 top-k 반환.

`GCSMemoryStore`는 세션 스코프 내 중복 GCS 호출을 방지하기 위해 `_cache: dict[UUID, dict[str, bytes]]` 인메모리 캐시를 유지한다.

**Debounce 정책**: `UpdateUserMemoryUseCase`는 LLM 호출 전 `.debounce.json` blob을 `if_generation_match` CAS로 원자적 선점한다 (claim-first). 마지막 claim으로부터 **5분** 이내면 선점 없이 즉시 반환. Modal 멀티 인스턴스 환경에서도 LLM 윈도우당 1회 호출을 보장하며, 루프 중간 부분쓰기 불일치를 원천 차단한다.

---

## 7. 합의된 변경사항

| 항목 | 변경 전 | 변경 후 | 사유 |
|------|---------|---------|------|
| 모듈 구조 | 단일 ComposeWorkflowUseCase | Main Orchestrator + 3 Sub-Agent | Sprint 3 신정혜 단독 배포 병목 해소, 단일 책임 원칙 |
| application 폴더 | `application/use_cases/` | `application/agents/{orchestrator,workflow_composer,skills_builder,personalization}/` | sub-agent 경계 명시 |
| Personalization 저장소 | (없음) | GCS 파일 (MEMORY.md 패턴) | 사용자가 Claude Code memory 시스템과 동일 포맷 명시 요청 |
| 신규 Port | (없음) | `PersonalMemoryStore`, (선택) `SubAgentClient` | GCS 어댑터 추상화 (Embedder는 nodes_graph 소유 `EmbedderPort` 재사용, PR #30 5/12 결정) |
| api_server 경계 | 직접 import | HTTP 어댑터 (`OrchestratorClient`) | sub-agent가 Modal app로 분리되어 in-process 호출 불가 |
| AgentState | 동일 | `personal_memory: list[MemoryEntry]` 필드 추가 | Orchestrator → Composer 전달용 |
| AgentMode | ONBOARDING/WIZARD/EDIT/GENERAL/SECURITY | + `SKILL_BUILDER` | Skills Builder 분기 표현 |
| AgentState 위치 | REQ-004 자체 정의 | REQ-012 common_schemas import | SSOT |
| WorkflowDraft / WorkflowNode / NodeDef | 별도 클래스 | `WorkflowSchema` / `NodeInstance` / `NodeConfig`로 통합 | SSOT |
| MemoryEntry.source_session_id | 없음 | `Optional[UUID]` 추가 | 메모리 출처 추적 |
| NodeRegistry | 독립 서비스 | Facade (NodeDefinitionRepository DI 주입) | Clean Architecture |

---

## 8. 의존성 관계

### 8.1 이 모듈이 import하는 대상

```python
# common_schemas (REQ-012)
from common_schemas import (
    AgentState, DraftSpec, IntentResult, SlotFillingState,
    UnresolvedNode, MemoryEntry, WorkflowSchema, NodeInstance, NodeConfig,
    Edge, Position, HandoffPayload, EvaluationResult, DocumentBlock,
)
from common_schemas.agent_protocol import AgentProtocolRequest, AgentProtocolResponse
from common_schemas.enums import AgentMode, ExecutionStatus, RiskLevel
from common_schemas.exceptions import ValidationError, DomainError
from common_schemas.transport import SSEFrame, AgentNodeFrame, SessionFrame

# auth (REQ-002) — domain/services만
from auth.domain.services import CredentialInjectionService

# nodes_graph (REQ-003) — domain/ports + domain/services만
from nodes_graph.domain.ports import NodeDefinitionRepository
from nodes_graph.domain.services import GraphValidator
```

### 8.2 이 모듈의 Port를 구현하는 외부 모듈

| Port | 구현 모듈 | 비고 |
|------|-----------|------|
| `AgentMemoryRepository` | `modules/storage/repositories/` | RDB |
| `WorkflowRepository` | `modules/storage/repositories/` | RDB |
| `PersonalMemoryStore` | `modules/ai_agent/adapters/memory/` | **자체 어댑터 (GCS)** — storage 모듈 경유 X |

### 8.3 이 모듈을 호출하는 외부 컨슈머

| 컨슈머 | 경로 | 비고 |
|--------|------|------|
| `services/api_server/` | HTTP → `orchestrator` Modal app `/v1/agent/route` | **in-process import 금지**. `services/api_server/adapters/orchestrator_client.py`가 HTTP 어댑터 |
| `modules/storage/` | `ai_agent.domain.ports.AgentMemoryRepository`, `WorkflowRepository` (ABC 구현용) | |
| `services/execution_engine/` | (간접) `HandoffPayload`를 통해 workflow_id 전달 | |

### 8.4 sub-agent 간 통신

- **금지**: `from ai_agent.application.agents.composer import ComposeWorkflowUseCase` (orchestrator에서)
- **허용**: `from ai_agent.adapters.agent_clients import HTTPSubAgentClient` → HTTP 호출

이 규칙은 PR 리뷰 시 import 그래프로 검증한다.

---

## 9. 테스트 전략

```
tests/
├── unit/
│   ├── domain/
│   │   ├── test_intent_analyzer_service.py    # LLMPort mock
│   │   ├── test_drafter_service.py            # LLMPort mock
│   │   ├── test_qa_evaluator_service.py       # LLMPort mock, score 경계값
│   │   ├── test_slot_filling_service.py       # 순수 로직, mock 불필요
│   │   ├── test_memory_entry.py               # entity validation
│   │   ├── test_personal_skill.py             # 신규
│   │   ├── test_skill_node.py                 # 신규
│   │   └── test_value_objects.py
│   └── application/
│       ├── orchestrator/
│       │   └── test_route_request_use_case.py        # IntentAnalyzer/SubAgentClient mock
│       ├── workflow_composer/
│       │   ├── test_compose_workflow_use_case.py     # Port 전부 mock
│       │   └── test_continue_conversation_use_case.py
│       ├── skills_builder/
│       │   ├── test_build_from_sop_use_case.py       # LLMPort/NodeDefinitionRepository mock
│       │   └── test_build_from_industry_default_use_case.py
│       └── personalization/
│           ├── test_load_user_memory_use_case.py     # PersonalMemoryStore mock
│           ├── test_update_user_memory_use_case.py
│           ├── test_recall_personal_skills_use_case.py
│           └── test_save_memory_use_case.py
└── integration/
    ├── test_langgraph_supervisor.py               # Orchestrator supervisor 흐름 (HTTP stub)
    ├── test_langgraph_composer.py                 # Composer 13-노드 흐름 (LLM mock)
    ├── test_gcs_memory_store.py                   # 실 GCS 또는 fake_gcs
    ├── test_node_registry_adapter.py              # NodeDefinitionRepository mock
    └── test_inter_agent_protocol.py               # AgentProtocolRequest/Response 직렬화 왕복
```

---

## 10. 파일 배치

```
modules/ai_agent/
├── __init__.py
├── domain/
│   ├── entities/
│   │   ├── memory_entry.py            # MemoryEntry
│   │   ├── conversation_message.py    # ConversationMessage
│   │   ├── personal_skill.py          # PersonalSkill (신규)
│   │   ├── skill_node.py              # SkillNode (신규)
│   │   └── session_ref.py             # SessionRef (신규) — 세션 인덱스 항목
│   ├── value_objects/
│   │   ├── turn_limit.py
│   │   └── quality_threshold.py
│   ├── services/
│   │   ├── intent_analyzer_service.py
│   │   ├── drafter_service.py
│   │   ├── qa_evaluator_service.py
│   │   ├── slot_filling_service.py
│   │   ├── workflow_layout_service.py    # 캔버스 노드 좌표 자동 배치 (Kahn's algorithm)
│   │   └── workflow_diff_service.py      # WorkflowDiffService (신규) — draft vs final 구조적 비교
│   └── ports/
│       ├── llm_port.py
│       │                              # (EmbedderPort는 nodes_graph/domain/ports 소유, ai_agent는 import만 — PR #30 5/12 결정)
│       ├── agent_memory_repository.py
│       ├── personal_memory_store.py   # PersonalMemoryStore (신규)
│       ├── session_frame_store.py     # SessionFrameStore (신규) — 세션 SSE 프레임 저장소
│       ├── workflow_draft_store.py    # WorkflowDraftStore (신규) — draft 임시 보관 Port
│       ├── workflow_repository.py
│       ├── node_registry.py
│       └── sub_agent_client.py        # SubAgentClient (신규, 선택)
├── application/
│   └── agents/                        # ⇐ 신규 구조
│       ├── orchestrator/
│       │   └── route_request_use_case.py
│       ├── workflow_composer/
│       │   ├── compose_workflow_use_case.py
│       │   ├── continue_conversation_use_case.py
│       │   └── approve_workflow_use_case.py      # 신규 (PR #135) — 사용자 승인 diff 처리
│       ├── skills_builder/
│       │   ├── build_from_sop_use_case.py
│       │   └── build_from_industry_default_use_case.py
│       └── personalization/
│           ├── load_user_memory_use_case.py
│           ├── update_user_memory_use_case.py
│           ├── recall_personal_skills_use_case.py
│           └── save_memory_use_case.py
├── adapters/
│   ├── llm/
│   │   ├── modal_llm_adapter.py
│   │   └── modal_embedding_adapter.py        # 신규
│   ├── memory/
│   │   ├── gcs_memory_store.py               # 신규 (PersonalMemoryStore 구현)
│   │   ├── gcs_session_frame_store.py        # 신규 (SessionFrameStore 구현 — 모니터링 히스토리)
│   │   └── in_memory_draft_store.py          # 신규 (PR #135, WorkflowDraftStore in-memory 구현)
│   ├── agent_clients/                        # 신규 (orchestrator 전용)
│   │   └── http_sub_agent_client.py
│   ├── langgraph/
│   │   ├── supervisor_graph.py               # Orchestrator
│   │   └── composer_graph.py                 # Workflow Composer 16-노드 (PR #135)
│   └── node_registry_adapter.py
├── seeds/
│   ├── industry_defaults/                    # 신규 (Skills Builder seed — 산업 baseline)
│   │   ├── ecommerce.json                    # 활성 (Sprint 3 데모 baseline)
│   │   ├── manufacturing.json                # 비활성 (Sprint 3 v1 베타, seed 보존)
│   │   ├── service.json                      # 비활성 (동상)
│   │   ├── wholesale_retail.json             # 비활성
│   │   ├── food.json                         # 비활성
│   │   └── it.json                           # 비활성
│   └── functional_domain_defaults/           # 신규 (Skills Builder seed — 직무 영역 baseline)
│       ├── customer_support.json
│       ├── it_ops.json
│       ├── document_data.json
│       ├── hr.json
│       └── marketing.json
├── tests/
│   ├── unit/
│   │   ├── domain/
│   │   └── application/
│   │       ├── orchestrator/
│   │       ├── workflow_composer/
│   │       ├── skills_builder/
│   │       └── personalization/
│   └── integration/
└── README.md
```

---

## 11. 변경 이력

| 일자 | 변경 | 담당 |
|------|------|------|
| 2026-05-05 | 클래스 다이어그램 교차분석 확정본 (단일 ComposeWorkflowUseCase) | 황대원 |
| 2026-05-11 | Sprint 3 멀티 에이전트 구조 전환 — Main Orchestrator + 3 Sub-Agent, PersonalMemoryStore 신규, GCS 어댑터, inter-agent HTTP 계약. (당시 EmbeddingPort 신규 명시했으나 2026-05-12 박아름 결정으로 nodes_graph `EmbedderPort`로 통합, 예외 패턴) | 황대원 |
| 2026-05-12 | **EmbedderPort SSOT 결정** — ai_agent에 별도 `EmbeddingPort` 신설 폐기, nodes_graph 소유 `EmbedderPort` 1개로 통합. 구현체만 ai_agent (`adapters/llm/modal_embedding_adapter.py`)가 소유하는 예외 패턴. 이유: 의존성 역전 위반 회피 — `nodes_graph → ai_agent` 의존 차단. 조장 후속 확인 (PR #54 embedder_port shim revert 요청) | 박아름 |
| 2026-05-12 | common_schemas Sprint 3 신규 타입 구현 — `agent_protocol.py`(AgentProtocolRequest/Response), `MemoryEntry` SSOT 이관, `AgentMode.SKILL_BUILDER`, `IntentResult.intent="build_skill"`, `AgentState.personal_memory`. PR: `feature/req-012-agent-protocol`. | 황대원 |
| 2026-05-15 | **Personalization 저장 구조 개선** — ① GCSMemoryStore Session Cache (`_cache: dict[UUID, list[PersonalSkill]]`) 구현 완료: 세션 내 GCS 중복 호출 제거, `save_entry()` 시 캐시 갱신. ② Content Hash Dedupe 제거: 중복 저장 방지 목적의 hash 비교 로직을 단순화 (Debounce P-4a로 대체 예정). ③ EmbeddingPort SSOT 이관: `ai_agent/domain/ports/embedding_port.py` 폐기, `nodes_graph.domain.ports.EmbedderPort` 사용으로 통일. | 이가원 |
| 2026-05-18 | **Personalization MemoryFile 기반 전면 재설계 반영 (PR #71)** — `PersonalMemoryStore` Port를 MemoryFile 기반 8메서드로 확정 (`load/save_index`, `load/save/delete_file`, `load/save_embedding`, `cleanup`). `UpdateUserMemoryUseCase` 시그니처 변경: `turn_count` 파라미터 추가, threshold(3) 미만·workflow 없으면 early return, 반환값 `bool`로 변경. `cleanup_memory` action 엔드포인트 추가 (`agent-personalization/main.py`). | 이가원 |
| 2026-05-21 | **사용자 승인 diff 흐름 추가 (PR #133, §3.3)** — 햄햄(이가원) 제안. `WorkflowDiffService`(domain/services, draft vs final 구조적 비교), `WorkflowDraftStore` Port(domain/ports, draft 임시 보관) 신규 구현. 단위 테스트 9건 완료. Personalization Agent 승인 이벤트 수신 + diff→memory 변환은 햄햄 담당. | 신정혜 |
| 2026-05-21 | **실행 검증 흐름 추가 (PR #135, §3.2)** — Composer 13→16노드 확장. `execute_node`(실행 엔진 HTTP 호출+폴링), `evaluate_output_node`(LLM 산출물 퀄리티 평가), `user_confirm_node`(결과 프레임 emit) 신규. `promote_node` WorkflowDraftStore 연동, `validator_node` RiskLevel 강제, `handoff_node` saved_workflow_id 상태 저장. `InMemoryWorkflowDraftStore` 어댑터, `ApproveWorkflowUseCase`, `POST /v1/agent/approve` 엔드포인트 구현. 단위 테스트 13건. 환경변수 `EXECUTION_ENGINE_URL` 추가(팀장님 Secret Manager 등록 필요). | 신정혜 |
| 2026-05-21 | **Personalization debounce claim-first 재설계 (PR #122)** — `PersonalMemoryStore` Port에 `claim_debounce_window(user_id, now, window) -> bool` 추가. `GCSMemoryStore`에서 `.debounce.json` blob을 `if_generation_match` CAS로 LLM 호출 전 선점. `UpdateUserMemoryUseCase` 흐름 재배치: CAS claim → 파일 로드 → LLM → 쓰기. 기존 `MemoryFile.updated_at` 기반 debounce 제거. debounce 정책: **5분**. | 이가원 |
