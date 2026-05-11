# Sprint 3 Plan — 멀티 에이전트 구조 전환 + 풀스택 MVP 배포

> 기간: 2026-05-11(월) ~ 2026-05-31(일), 21일
> 목표: GCP Cloud Run 배포 완료, 외부 도메인 접근 가능, 4개 화면 동작, Modal GPU + Gemma 4 + BGE-M3 실연동의 풀스택 MVP

---

## 1. 핵심 결정사항 (Sprint 3 시작 전 합의)

| 항목 | 결정 |
|------|------|
| 완성 기준 | GCP 배포 + 외부 접근 가능 (Cloud Run 도메인) |
| Frontend 범위 | 4개 화면 모두 (Canvas + Chat + Execution + Document Viewer) |
| LLM 통합 깊이 | Modal GPU + Gemma 4 + BGE-M3 풀스택 |
| ai_agent 구조 | **멀티 에이전트로 전환** — Main Orchestrator + 3 Sub-Agent |
| Sub-Agent 배포 구조 | **에이전트별 Modal app + HTTP 통신 (옵션 2)** — 각 멤버가 본인 에이전트 자율 배포 |
| Modal app 간 인증 | **VPC 내부 통신만 허용 (옵션 C)** — 외부 차단, 인증 없음 |
| Skills Builder 입력 채널 | Frontend Document Viewer에 통합 ("이 문서로 skills 생성" 버튼) |
| 산업 표준 default | Seed 5개 산업 (제조/서비스/도소매/음식점/IT) — 박아름 작성, LLM 자유생성은 v2 |
| Personalization 저장 | GCS 파일 기반 (Claude Code memory.md 패턴 — `MEMORY.md` 인덱스 + 개별 `.md`) |

---

## 2. 멀티 에이전트 구조

### 2.1 에이전트 분장

| 에이전트 | 역할 | 담당자 | Modal app 이름 |
|---------|------|--------|---------------|
| **Main Orchestrator** | LangGraph supervisor, sub-agent 라우팅, personal memory 로드 | 신정혜 | `orchestrator` |
| **Workflow Composer** | 사용자 채팅 → 워크플로우 초안·완성 | 신정혜 | `agent-composer` |
| **Skills Builder** | SOP 문서/산업 default → skills 노드 생성 | 박아름 | `agent-skills-builder` |
| **Personalization** | 사용자 패턴 추출 → memory.md 갱신·로드 | 햄햄(이가원) | `agent-personalization` |
| **LLM Base** | Gemma 4 inference + BGE-M3 embedding | 신정혜 | `llm-base` |

### 2.2 Modal Workspace 구조

```
Modal workspace: workflow-automation (VPC 내부 통신만)
├── app: llm-base                    ← 신정혜 (5/12 1회 배포 후 안정)
├── app: orchestrator                ← 신정혜 (LangGraph supervisor)
├── app: agent-composer              ← 신정혜
├── app: agent-skills-builder        ← 박아름
└── app: agent-personalization       ← 햄햄
```

각 멤버는 본인 에이전트 코드 수정 후 `modal deploy` 자율 실행. 다른 멤버 영향 없음.

### 2.3 코드 레이아웃

```
modules/ai_agent/
├── domain/
│   ├── entities/          # AgentState, MemoryEntry, PersonalSkill, SkillNode
│   ├── ports/             # LLMPort, EmbeddingPort, AgentMemoryRepository, PersonalMemoryStore (신규)
│   └── services/          # IntentAnalyzer, DrafterService, QAEvaluator, SlotFilling (기존)
├── application/
│   └── agents/            # 신규 — sub-agent별 use case 묶음
│       ├── orchestrator/
│       │   └── route_request_use_case.py
│       ├── workflow_composer/
│       │   ├── compose_workflow_use_case.py
│       │   └── continue_conversation_use_case.py
│       ├── skills_builder/
│       │   ├── build_from_sop_use_case.py
│       │   └── build_from_industry_default_use_case.py
│       └── personalization/
│           ├── load_user_memory_use_case.py
│           ├── update_user_memory_use_case.py
│           └── recall_personal_skills_use_case.py
└── adapters/
    ├── langgraph/         # Main Orchestrator supervisor graph
    ├── llm/modal_*        # Modal Gemma 4 + BGE-M3 어댑터
    └── memory/            # PersonalMemoryStore 구현
        └── gcs_memory_store.py
```

### 2.4 Inter-Agent 통신 계약 (5/12 sync에서 확정)

`common_schemas/agent_protocol.py`에 정의 (전 sub-agent 공통):

```python
# 입력
{
  "session_id": "uuid",
  "user_id": "uuid",
  "state": AgentState,           # common_schemas
  "personal_memory": list[MemoryEntry]
}

# 출력
{
  "frames": list[SSEFrame],      # 9종 transport frame
  "state_delta": dict,
  "next_action": "continue" | "complete" | "error"
}
```

### 2.5 Personalization Agent — Claude Code memory 패턴

GCS user별 prefix에 저장:

```
gs://workflow-automation-personal/
  users/{user_id}/
    MEMORY.md              # 인덱스
    user_role.md           # type: user
    workflow_patterns.md   # type: feedback
    favorite_nodes.md      # type: project
    integrations.md        # type: reference
```

발동:
- 세션 시작: `LoadUserMemoryUseCase` → Orchestrator state에 주입
- 워크플로우 완료: `UpdateUserMemoryUseCase` → LLM이 패턴 추출 → 새 .md 작성/갱신

---

## 3. Phase 분할 (클린아키텍처 단계 정렬)

| Phase | 기간 | 일수 | 핵심 산출물 | 상태 |
|-------|------|-----|-----------|------|
| **A1** | ~5/10 | — | `packages/common_schemas/` + `modules/*/domain/` + `modules/*/application/` | ✅ 완료 |
| **A2** | 5/11(월) ~ 5/17(일) | 7d | `modules/*/adapters/` + `services/api_server` composition root + 5개 Modal app 배포 + common_schemas 신규 타입 | **이번 1주차** |
| **A3** | 5/18(월) ~ 5/19(화) | 2d | integration test + Phase A 게이트 (5개 Modal app + api_server `/health`·`/auth` 동작) | 예정 |
| **B** | 5/20(수) ~ 5/27(수) | 8d | API 라우터 + Frontend 4화면 (Canvas + Chat + Execution + Document Viewer) | 예정 |
| **C** | 5/28(목) ~ 5/31(일) | 4d | GCP 배포 + Polish + 데모 | 예정 |

### 3.1 의존성 순서 (클린아키텍처 원칙)

```
A1 (완료)              A2 (이번 1주차)           A3 (2주차 시작)
─────────────────      ─────────────────         ─────────────────
schemas                adapters                   integration test
  ↓                      ↓                         ↓
domain                 Modal app 배포              Phase A 게이트
  ↓                      ↓                         (5개 app + api_server)
application            api_server composition
                       Repository 구현체
```

A2 부터는 **외부 시스템 연동(Modal, GCS, PostgreSQL, HTTP)**을 도입한다. 각 멤버는 본인 Port의 ABC 계약은 이미 확정되어 있으니, **구현체만** 작성하면 된다. 새로 추가되는 Port는 5/11 sync에서 합의.

---

## 4. Phase A2 — 1주차 adapter 작업 분배 (5/11~5/17)

### 4.0 1주차 핵심 산출물 체크리스트

| 영역 | 결과물 | 담당 |
|------|-------|------|
| common_schemas 신규 | `agent_protocol.py` (AgentProtocolRequest/Response), `AgentMode.SKILL_BUILDER`, `IntentResult.intent` Literal `"build_skill"` 추가, `AgentState.personal_memory` 필드 | 황대원 |
| nodes_graph adapters | `catalog/` 36개 노드 구현체 + Plugin discovery + UPSERT | 박아름 |
| ai_agent adapters (LLM) | `adapters/llm/modal_llm_adapter.py` + `modal_embedding_adapter.py` | 신정혜 |
| ai_agent adapters (orchestrator/composer) | `adapters/langgraph/{supervisor_graph,composer_graph}.py` + `adapters/agent_clients/http_sub_agent_client.py` + `adapters/node_registry_adapter.py` | 신정혜 |
| ai_agent skills_builder | Skills Builder use case 본격 구현 + `seeds/industry_defaults/*.json` (5종) | 박아름 |
| ai_agent personalization | Personalization use case 본격 구현 + `adapters/memory/gcs_memory_store.py` | 햄햄(이가원) |
| toolset adapters | `adapters/tools/` 8 connectors | 햄햄(이가원) |
| storage Repository | 9종 Pg*Repository 구현체 | 황대원 |
| api_server composition | FastAPI 골격 + DI 컨테이너 + `adapters/orchestrator_client.py` + `/health`·`/auth` 라우터 | 황대원 |
| doc_parser SSOT | `Chunk`/`ChunkingStrategy`/`QualityGateResult`/`QualityMetrics`/`WarningInfo` → common_schemas 이관 | 김진형 |
| Modal app 배포 | 5개 app (`llm-base`, `orchestrator`, `agent-composer`, `agent-skills-builder`, `agent-personalization`) | 각 담당자 |

### 4.1 의존성 그래프 (1주차)

```
[5/12 sync 산출물]
common_schemas.agent_protocol  ─┐
                                │ (모든 sub-agent가 요청·응답 직렬화에 필요)
                                ▼
[신정혜] llm-base Modal 배포 ──► LLM_BASE_URL 환경변수 공유
                                │
                                ▼
[병렬]
  신정혜: composer/orchestrator adapter + LangGraph
  박아름: skills_builder adapter + nodes_graph 카탈로그
  햄햄:    personalization adapter + GCS + toolset connectors
  황대원: storage Repository + api_server composition
  김진형: doc_parser SSOT 이관

[5/16~5/17 통합]
  각 Modal app 배포 → HTTP endpoint 확보
  api_server OrchestratorClient ↔ orchestrator Modal app smoke test
```

> 각 sub-agent 어댑터는 `domain/ports/`의 ABC를 구현하므로 **다른 멤버 작업에 차단되지 않음**. 단 `llm-base` Modal 배포(5/12 저녁)는 LLMPort/EmbeddingPort 어댑터의 endpoint를 제공하므로 **5/12 이후 다른 멤버 작업의 dependency**. 신정혜가 슬립 시 stub LLM(echo) 어댑터로 대체.

### 4.2 멤버별 일자별 작업

#### 황대원 (조장) — common_schemas + storage Repository + api_server composition

| 일자 | 작업 | 산출물 |
|------|------|--------|
| 5/11(월) | Sprint 3 kickoff standup 진행 (15분) · cross-cutting interface sync 주관 (1.5h) — agent_protocol schema 확정 · Modal workspace 멤버 권한 추가 + GCP IAM | sync 의사록 PR (`docs/context/decisions.md`), Modal workspace 권한 |
| 5/12(화) | common_schemas 신규 타입 PR — `agent_protocol.py` (AgentProtocolRequest/Response), `AgentMode.SKILL_BUILDER`, `IntentResult.intent` Literal에 `"build_skill"`, `AgentState.personal_memory: list[MemoryEntry]` · api_server `app/main.py` FastAPI 골격 (lifespan, settings, structured logging) | `feature/req-012-agent-protocol`, `feature/req-009-api-server-skeleton` |
| 5/13(수) | api_server `app/dependencies/container.py` DI 컨테이너 (DependencyContainer 클래스) · 전역 에러 핸들러 (`infrastructure/error_handlers.py`) · `auth.adapters.middleware`를 활용한 JWT 미들웨어 통합 | `feature/req-009-api-server-skeleton` 연속 |
| 5/14(목) | api_server `app/adapters/orchestrator_client.py` — HTTP 어댑터 (httpx AsyncClient, SSE 디코딩, `AgentProtocolRequest/Response` 직렬화, `ORCHESTRATOR_URL` env 사용) · `app/sse/sse_encoder.py` (SSEFrame → text/event-stream) | `feature/req-009-orchestrator-client` |
| 5/15(금) | storage `Pg*Repository` 1차 (auth/nodes_graph 용) — `PgSessionRepository`, `PgOAuthRepository`, `PgNodeDefinitionRepository`. asyncpg + SQLAlchemy + 도메인 엔티티 ↔ ORM mapper | `feature/req-008-storage-repositories` |
| 5/16(토) | storage `Pg*Repository` 2차 — `PgAgentMemoryRepository`, `PgWorkflowRepository`, `PgExecutionRepository`, `PgDocumentRepository`, `PgToolExecutionRepository`, `PgSkillRepository` | `feature/req-008-storage-repositories` 연속 |
| 5/17(일) | api_server `app/routers/health.py` + `auth.py` 라우터 (login, refresh, oauth callback) · pydantic2ts TypeScript 코드젠 스크립트 (`packages/common_schemas/scripts/generate_ts.py`) | `feature/req-009-api-server-routers`, `feature/req-012-codegen` |

**총 작업량**: 7일 (Phase A2 풀 가동, frontend 공통/Terraform는 Phase B로 이연)

#### 신정혜 — Main Orchestrator + Workflow Composer + LLM base

| 일자 | 작업 | 산출물 |
|------|------|--------|
| 5/11(월) | Sprint 3 kickoff 참여 · inter-agent 통신 계약 sync 참여 (확정 안 작성) · ai_agent adapter 작업 시작 전 design note (`docs/context/decisions.md`에 LangGraph supervisor 패턴 결정) | design note PR |
| 5/12(화) | **Modal app template** 작성 — 1개 sample (`agent-composer`)로 다른 멤버가 fork 가능한 형태. requirements, secret 마운트, healthcheck endpoint 패턴 · **저녁: `llm-base` Modal app 배포** — Gemma 4 + BGE-M3 단일 endpoint (`/v1/llm/generate`, `/v1/embeddings`) | Modal app template + `llm-base` 배포 완료 |
| 5/13(수) | `adapters/llm/modal_llm_adapter.py` (LLMPort 구현 — httpx, retry, circuit breaker, `LLM_BASE_URL` env) · `adapters/llm/modal_embedding_adapter.py` (EmbeddingPort 구현 — 768d BGE-M3) | `feature/req-004-llm-adapters` |
| 5/14(목) | `adapters/langgraph/composer_graph.py` — Workflow Composer 13-노드 StateGraph 빌드 · `ComposeWorkflowUseCase` 본격 구현 (현재 sequential을 LangGraph 호출로 교체) | `feature/req-004-composer-graph` |
| 5/15(금) | `adapters/langgraph/supervisor_graph.py` — Orchestrator supervisor (load_memory → intent → composer/skills/finalize → update_memory) · `RouteRequestUseCase` 본격 구현 | `feature/req-004-orchestrator-graph` |
| 5/16(토) | `adapters/agent_clients/http_sub_agent_client.py` (SubAgentClient HTTP 구현, `COMPOSER_URL`/`SKILLS_BUILDER_URL`/`PERSONALIZATION_URL` env) · `adapters/node_registry_adapter.py` (nodes_graph Facade — `NodeDefinitionRepository` DI 주입) | `feature/req-004-sub-agent-client` |
| 5/17(일) | **`agent-composer` Modal app 배포** · **`orchestrator` Modal app 배포** · 두 app HTTP 호출 smoke test (composer endpoint 단독 호출 + orchestrator → composer 라우팅) | 2개 Modal app 배포 완료 |

**총 작업량**: 7일 (LLM base + 2개 Modal app 배포가 임계 경로 — 5/12 슬립 시 stub 어댑터로 다른 멤버 unblock)

#### 박아름 — nodes_graph 36개 노드 + Skills Builder Agent

| 일자 | 작업 | 산출물 |
|------|------|--------|
| 5/11(월) | kickoff + cross-cutting sync 참여 · nodes_graph 현재 카탈로그 상태 점검 (현재 `catalog/external/`에 http_request, pdf_generate만) · Plugin discovery 패턴 설계 노트 | review note |
| 5/12(화) | **09:00 sync** (30분, 김진형과): doc_parser 출력 DocumentBlock ↔ Skills Builder 입력 인터페이스 확정 · **오후 sync** (1h, 신정혜·햄햄): inter-agent 통신 계약 · nodes_graph catalog **Category 1: Communication** — Slack, Gmail, Outlook, Teams 4종 NodeDefinition + BaseNode 상속 구현 | `feature/req-003-catalog-communication` |
| 5/13(수) | nodes_graph catalog **Category 2: Document** — Google Drive, Sheets, Docs, OneDrive 4종 | `feature/req-003-catalog-document` |
| 5/14(목) | nodes_graph catalog **Category 3-5**: Data (PostgreSQL, BigQuery, MySQL), AI/ML (OpenAI, Anthropic), Productivity (Notion, Calendar, Linear) 9종 · Plugin discovery (`modules/nodes_graph/adapters/catalog/registry.py`) — 카탈로그 자동 등록 + BGE-M3 임베딩 (신정혜의 ModalEmbeddingAdapter 활용) + `NodeDefinitionRepository.upsert()` | `feature/req-003-plugin-discovery` |
| 5/15(금) | nodes_graph 잔여 카테고리 (Webhook, Schedule, Filter, Transform 등) · **산업 default seed 5개 작성** — `modules/ai_agent/seeds/industry_defaults/{manufacturing,service,wholesale_retail,food,it}.json`. 각 산업별 5~7개 SkillNode (총 25~35개) | `feature/req-003-catalog-misc`, seed JSON |
| 5/16(토) | `BuildFromIndustryDefaultUseCase` 본격 구현 — seed JSON 로드 → SkillNode 검증 → NodeDefinitionRepository.upsert() 일괄 등록 · `BuildFromSOPUseCase` 본격 구현 — LLM 호출 (LLMPort)하여 DocumentBlock → SkillNode 추출 → upsert | `feature/req-004-skills-builder-usecase` |
| 5/17(일) | **`agent-skills-builder` Modal app 배포** · integration test (sample SOP DocumentBlock 입력 → upsert까지 e2e) · `BuildFromSOPUseCase`에서 SSE 프레임 yield 확인 | Modal app 배포 + e2e test |

**총 작업량**: 7일 (nodes_graph 카탈로그 36개가 분량 — Communication/Document/Data 13개 우선, MVP 외 노드는 Sprint 4 이연 가능)

#### 햄햄(이가원) — toolset connectors + Personalization Agent

| 일자 | 작업 | 산출물 |
|------|------|--------|
| 5/11(월) | kickoff + inter-agent 통신 sync 참여 · GCS `workflow-automation-personal` 버킷 셋업 요청 (황대원에게 IAM) · toolset 현재 상태 점검 (`adapters/tools/` 비어있음) | sync 참여, GCS 버킷 생성 |
| 5/12(화) | **오후 sync** (1h, 신정혜·박아름): inter-agent 통신 계약 · toolset connector 1: `adapters/tools/slack_tool.py` (Slack chat.postMessage, `SecureConnectorPort` DI) · toolset connector 2: `adapters/tools/http_request_tool.py` (generic HTTP) | `feature/req-005-toolset-slack-http` |
| 5/13(수) | toolset connector 3: `adapters/tools/webhook_tool.py` · `PersonalMemoryStore` Port 정의 (`modules/ai_agent/domain/ports/personal_memory_store.py`) — ABC 메서드 시그니처 확정 | `feature/req-005-toolset-webhook`, `feature/req-004-personal-memory-port` |
| 5/14(목) | `adapters/memory/gcs_memory_store.py` — PersonalMemoryStore 구현 (google-cloud-storage, MEMORY.md 인덱스 파싱, frontmatter 추출/직렬화) · GCS 버킷 권한 검증 | `feature/req-004-gcs-memory` |
| 5/15(금) | `LoadUserMemoryUseCase` 본격 구현 — MEMORY.md 인덱스 → 본문 .md 파일들 로드 → list[MemoryEntry] 반환 · `RecallPersonalSkillsUseCase` 본격 구현 — query 임베딩 + 각 entry description 임베딩 코사인 유사도 top-k (EmbeddingPort 사용) | `feature/req-004-personalization-load-recall` |
| 5/16(토) | `UpdateUserMemoryUseCase` 본격 구현 — workflow 완료 → LLM 패턴 추출 (LLMPort) → frontmatter 포맷팅 → GCS 저장 · toolset connector 4: `adapters/tools/gmail_tool.py` | `feature/req-004-personalization-update`, `feature/req-005-toolset-gmail` |
| 5/17(일) | **`agent-personalization` Modal app 배포** · toolset connector 5: `adapters/tools/google_sheets_tool.py` (시간 여유 시 6: Drive, 7: Notion까지) · Personalization integration test (mock GCS or fake_gcs) | Modal app 배포 + 5~7개 connector |

**총 작업량**: 7일 (Personalization 4 use case + toolset 5~7 connector. Modal 배포는 5/17 단일 — 슬립 시 5/18로 이연)

#### 김진형 — doc_parser SSOT 이관 + 데모 시나리오

| 일자 | 작업 | 산출물 |
|------|------|--------|
| 5/11(월) | kickoff 참여 · doc_parser 현재 상태 확인 (REQ-006 완성도 — adapters/parsers/ 8종 구현됨, 테스트 43 passed) · 이관 대상 클래스 식별 (`Chunk`, `ChunkingStrategy`, `QualityGateResult`, `QualityMetrics`, `WarningInfo`) | review note |
| 5/12(화) | **09:00 sync** (30분, 박아름과): Skills Builder가 소비하는 DocumentBlock 필드 확정 · common_schemas 이관 1차: `Chunk` + `ChunkingStrategy` → `packages/common_schemas/python/common_schemas/document.py` | `feature/req-012-doc-parser-ssot` |
| 5/13(수) | common_schemas 이관 2차: `QualityGateResult`, `QualityMetrics`, `WarningInfo` → `common_schemas.document` · doc_parser 내부 `from common_schemas import ...` import path 일괄 변경 | `feature/req-012-doc-parser-ssot` 연속 |
| 5/14(목) | doc_parser 회귀 테스트 — 기존 43 passed 유지 + 추가 (common_schemas import 검증) · storage 모듈의 `PgDocumentRepository`(황대원 5/16 작업)와의 인터페이스 사전 점검 | 회귀 테스트 통과 |
| 5/15(금) | **데모 시나리오 5개 초안 작성** — `docs/specs/demo_scenarios.md`. 5개 산업(제조/서비스/도소매/음식점/IT)별 SOP → Skills Builder → Workflow Composer → 실행 e2e 시나리오 · sample SOP 문서 3종 준비 (PDF/DOCX/HWP) | `docs/specs/demo_scenarios.md` |
| 5/16(토) | 데모 시나리오 5개 확정 — 박아름의 산업 default seed와 정합화 · sample SOP 문서 GCS 업로드 (`workflow-automation-uploads/demo/`) · 시나리오별 expected workflow_id 매핑 | 데모 문서 확정 |
| 5/17(일) | frontend document viewer 사전 학습 (Phase B 5/20~ 시작 대비 — React + react-pdf, mammoth.js, 또는 google-drive-viewer 후보 조사) · 박아름·햄햄 페어 지원 (시간 여유 시) | tech spike note |

**총 작업량**: 7일 (SSOT 이관 + 데모 자료. 박아름이 산업 seed 작성 중 도메인 지식 질문 발생 시 김진형이 지원)

### 4.3 1주차 마일스톤

| 일자 | 게이트 |
|-----|-------|
| 5/11(월) 09:00 | Sprint 3 kickoff standup + cross-cutting interface sync |
| 5/12(화) 09:00 | doc_parser ↔ Skills Builder ↔ nodes_graph 인터페이스 sync (박아름·김진형) |
| 5/12(화) 오후 | inter-agent 통신 계약 (`agent_protocol`) schema 확정 (신정혜·박아름·햄햄) |
| 5/12(화) 저녁 | **`llm-base` Modal app 배포 완료** (신정혜) — 다른 멤버 어댑터 작업의 endpoint 의존성 해소 |
| 5/13(수) | api_server FastAPI 골격 + `/health` 동작 (황대원) |
| 5/15(금) | 산업 default seed 5종 commit (박아름) · doc_parser SSOT 이관 PR (김진형) · 황대원 1차 Repository PR |
| 5/16(토) | GCS memory store 동작 검증 (햄햄) · 황대원 2차 Repository PR |
| **5/17(일)** | **5개 Modal app 전부 배포 완료** (신정혜 3 + 박아름 1 + 햄햄 1). api_server `/health`·`/auth` 라우터 동작. 1주차 종료 — Phase A3 진입 |

### 4.4 1주차 PR 흐름

병렬성 확보를 위해 멤버별 작은 PR 권장 (PR 24시간 룰):

| 담당 | PR 개수 (예상) | 핵심 PR |
|------|--------------|--------|
| 황대원 | 4~5개 | req-012-agent-protocol → req-009-api-server-skeleton → req-009-orchestrator-client → req-008-storage-repositories (1차/2차) → req-009-api-server-routers |
| 신정혜 | 4~5개 | req-004-llm-adapters → req-004-composer-graph → req-004-orchestrator-graph → req-004-sub-agent-client + Modal 배포 |
| 박아름 | 4~5개 | req-003-catalog-* (3건) → req-003-plugin-discovery → req-004-skills-builder-usecase + Modal 배포 |
| 햄햄 | 4~5개 | req-005-toolset-slack-http → req-004-personal-memory-port + gcs-memory → req-004-personalization-load-recall → req-004-personalization-update → 추가 toolset + Modal 배포 |
| 김진형 | 2~3개 | req-012-doc-parser-ssot (2건) → demo_scenarios.md |

---

## 5. Phase A3 — Integration Test + Phase A 게이트 (5/18~5/19)

### 5.1 5/18(월) — integration & 부족분 처리
- 5/17까지 미완료된 Modal app 배포 마무리
- sub-agent HTTP 호출 e2e: orchestrator → (composer / skills-builder / personalization)
- api_server OrchestratorClient ↔ orchestrator Modal smoke test (HTTP + SSE)
- 황대원·신정혜: api_server ↔ Orchestrator 통합 인터페이스 최종 합의

### 5.2 5/19(화) — Phase A 게이트
- 5개 Modal app 전부 배포 완료, sub-agent HTTP 호출 정상
- `orchestrator` ↔ `composer`/`skills-builder`/`personalization` 라우팅 동작
- api_server `/health`, `/auth` 라우터 + JWT 검증 동작
- common_schemas TypeScript 산출물 존재 (`packages/common_schemas/typescript/`)
- 모듈별 unit + integration test 통과
- doc_parser SSOT 이관 + 회귀 테스트 통과
- `feature/req-011-infra` 브랜치 baseline 작성 시작 (Phase B 후반 Terraform 작업 준비)

---

## 5. Phase B — API 라우터 + Frontend (5/20~5/27)

### 5.1 멤버별 일정

#### 신정혜 — frontend chat + Orchestrator 통합
- 5/20-21: chat 컴포넌트 + SSE 9종 프레임 렌더링
- 5/22-23: chat ↔ Orchestrator HTTP 통합
- 5/24-25: 슬롯 필링 UI + draft spec delta 표시
- 5/26-27: 통합 테스트

#### 박아름 — frontend canvas + workflows 라우터
- 5/20-22: React Flow canvas + 36 노드 표현 + 드래그/연결
- 5/23-24: api_server `/workflows` CRUD + `/validate` 라우터
- 5/25-26: Skills Builder UI 통합 (document viewer에 버튼)
- 5/27: 통합 테스트

#### 햄햄(이가원) — frontend execution + personal skills UI
- 5/20-22: execution monitoring (SSE 실행 진행상황)
- 5/23-24: personal skills 미리보기/편집 UI (memory.md 사용자 노출)
- 5/25-26: toolset 추가 connectors (필요시)
- 5/27: 통합 테스트

#### 김진형 — frontend document viewer + 데모
- 5/20-22: document viewer + 업로드 UI + 파싱 결과 표시
- 5/23-24: Skills Builder 입력 UI 통합
- 5/25: 데모 시나리오 5개 확정
- 5/26-27: 데모 리허설

#### 황대원 — SSE 라우터 + 프론트엔드 공통 + Terraform 착수
- 5/20-22: `/agents/sessions`, `/agents/.../stream`, `/executions/{id}` SSE 라우터
- 5/23: Zustand 스토어 + API client + `useSSEStream` hook
- 5/24-25: Terraform 모듈 작성 (`feature/req-011-infra` 브랜치) — Cloud Run × 3, Cloud SQL, Memorystore, Secret Manager, VPC Connector, IAM
- 5/26-27: GitHub Actions deploy 워크플로우

### 5.2 Phase B 게이트 (5/27)
- 로컬 docker-compose에서 e2e 데모 시나리오 5개 통과
- 4개 화면 모두 동작 (Canvas + Chat + Execution + Document)
- SSE 스트림 9종 프레임 전부 렌더링

---

## 6. Phase C — GCP 배포 + Polish (5/28~5/31)

| 날짜 | 작업 | 담당 |
|------|------|------|
| 5/28(목) | Terraform apply: Cloud SQL + Memorystore + Secret Manager + VPC | 황대원 + 박아름 |
| 5/28(목) | Modal 프로덕션 검증 + 부하 테스트 | 신정혜 + 햄햄 |
| 5/28(목) | 데모 시나리오 검증 (local) | 김진형 |
| 5/29(금) | Cloud Run 배포 + 도메인 연결 + IAM | 황대원 + 박아름 |
| 5/29(금) | 클라우드 환경 e2e 검증 | 팀 전원 |
| 5/30(토) | 버그 픽스 buffer day | 팀 전원 |
| 5/31(일) | 데모 리허설 + 발표 자료 마감 | 팀 전원 |

---

## 7. 멤버별 총 부담

| 담당자 | 일수 | 핵심 작업 |
|--------|-----|----------|
| 황대원 | 13d | api_server core + frontend 공통 + Terraform(`feature/req-011-infra`) + CI/CD + Modal workspace |
| 박아름 | 11.5d | nodes_graph + **Skills Builder Agent** + frontend canvas + workflows 라우터 |
| 신정혜 | 12d | **Main Orchestrator + Workflow Composer + LLM base** + frontend chat |
| 햄햄(이가원) | 10d | toolset + **Personalization Agent (memory.md GCS)** + frontend execution |
| 김진형 | 6d | doc_parser SSOT + frontend document + 데모 시나리오 |

---

## 8. 핵심 마일스톤

| 일자 | 게이트 | 단계 |
|-----|-------|-----|
| ~5/10 | schemas + domain + application 완료 | A1 (완료) |
| 5/11(월) 09:00 | Sprint 3 kickoff + cross-cutting interface sync | A2 |
| 5/12(화) 09:00 | doc_parser ↔ Skills Builder ↔ nodes_graph 인터페이스 sync | A2 |
| 5/12(화) 오후 | inter-agent 통신 계약 (`agent_protocol`) schema 확정 | A2 |
| 5/12(화) 저녁 | **`llm-base` Modal 배포 완료** (Gemma 4 + BGE-M3) | A2 |
| 5/13(수) | api_server FastAPI 골격 + `/health` 동작 | A2 |
| 5/15(금) | 산업 default seed 5종 + doc_parser SSOT 이관 PR | A2 |
| **5/17(일)** | **5개 Modal app 전부 배포 완료** + api_server `/health`·`/auth` 동작 | A2 종료 |
| **5/19(화)** | **Phase A 게이트** — sub-agent 라우팅 e2e + integration test 통과 | A3 |
| 5/22(금) | `useSSEStream` hook 배포 → 모든 frontend 화면이 SSE 사용 가능 | B |
| **5/27(수)** | **Phase B 게이트** — 로컬 docker-compose e2e 통과 | B |
| 5/29(금) | GCP Cloud Run 배포 + 외부 도메인 접속 가능 | C |
| **5/31(일)** | **최종 데모** | C |

---

## 9. 일일 운영

- 매일 09:00 standup (15분)
- Phase 게이트 일(5/19, 5/27)은 오후 2시간 통합 검증
- PR 24시간 룰 (같은 날 리뷰 끝내기)
- 5/12 standup은 30분 확장 (멀티에이전트 인터페이스 합의가 cross-cutting)

---

## 10. 리스크 & 대응

| 리스크 | 영향 | 대응 |
|-------|------|------|
| 신정혜 11d (Main+Composer+LLM base+Modal+Frontend chat) 임계 부담 | Phase A 게이트 슬립 | 5/12 저녁 Modal 배포 슬립 시 김진형이 5/18-19 페어 지원 |
| Modal app 5개 셋업 비용 | Phase A 초반 지연 | Modal app template 5/12-13 신정혜가 1개 작성 후 나머지 멤버는 fork |
| Skills Builder 산업 default 도메인 지식 부족 | 5/14-15 작업 슬립 | 박아름이 stakeholder 인터뷰 또는 ChatGPT로 1차 초안 빠르게 |
| Inter-agent HTTP 통신 분산 디버깅 | 통합 단계 디버깅 시간 ↑ | OpenTelemetry trace 헤더 5/12 계약에 포함, 모든 sub-agent 통과 시 trace_id 전파 |
| Terraform Cloud Run + Cloud SQL 처음 작성 | Phase C 슬립 | 황대원이 Phase B 후반(5/24-25)부터 미리 작성 시작 |
| 5/30(토) buffer 작업일 가용성 | 폴리시 부족 | 사전에 팀원 가용 확인 + 5/29 끝에 남은 작업 우선순위 합의 |

---

## 11. v2 (Sprint 4+) 미루기 항목

- LLM 자유 생성 기반 산업 default (Sprint 3는 seed 5개로 한정)
- Personalization Agent의 능동 학습 (Sprint 3는 워크플로우 완료 시점에만 갱신)
- Modal app 간 mTLS 인증 (Sprint 3는 VPC 내부 통신만)
- 워크플로우 버전 관리, A/B 테스트, 실행 히스토리 검색

---

## 12. 브랜치 전략

| 브랜치 | 용도 | 담당 |
|--------|------|------|
| `feature/req-004-ai-agent` | 멀티에이전트 재구성 (Phase A1) | 신정혜 (merged 2026-05-11) |
| `feature/req-004-llm-adapters` | ai_agent LLMPort/EmbeddingPort 어댑터 (A2) | 신정혜 |
| `feature/req-004-composer-graph` | Workflow Composer LangGraph 13-노드 (A2) | 신정혜 |
| `feature/req-004-orchestrator-graph` | Main Orchestrator supervisor (A2) | 신정혜 |
| `feature/req-004-sub-agent-client` | HTTPSubAgentClient + NodeRegistry Facade (A2) | 신정혜 |
| `feature/req-003-catalog-*` | nodes_graph 36개 노드 카탈로그 (A2) | 박아름 |
| `feature/req-003-plugin-discovery` | nodes_graph plugin discovery + UPSERT (A2) | 박아름 |
| `feature/req-004-skills-builder-usecase` | Skills Builder use cases + seeds (A2) | 박아름 |
| `feature/req-004-personal-memory-port` | PersonalMemoryStore Port + GCS 어댑터 (A2) | 햄햄 |
| `feature/req-004-personalization-*` | Load/Update/Recall use cases (A2) | 햄햄 |
| `feature/req-005-toolset-*` | toolset connectors 5~7종 (A2) | 햄햄 |
| `feature/req-012-doc-parser-ssot` | doc_parser SSOT 이관 (A2) | 김진형 |
| `feature/req-012-agent-protocol` | common_schemas agent_protocol 등 (A2) | 황대원 |
| `feature/req-009-api-server-skeleton` | FastAPI 골격 + DI 컨테이너 (A2) | 황대원 |
| `feature/req-009-orchestrator-client` | OrchestratorClient HTTP 어댑터 (A2) | 황대원 |
| `feature/req-008-storage-repositories` | 9종 Pg*Repository (A2) | 황대원 |
| `feature/req-009-api-server-routers` | /health, /auth 라우터 (A2) | 황대원 |
| `feature/req-009-api-server` | Phase B SSE/workflows/agents 라우터 | 황대원 |
| `feature/req-010-frontend` | frontend 4화면 (Phase B) | 팀 분담 |
| `feature/req-011-infra` | Terraform + Modal workspace (Phase B/C) | 황대원 |

---

## 13. 변경 이력

| 일자 | 변경 | 사유 |
|------|------|------|
| 2026-05-11 | 초안 작성 | Sprint 3 시작 |
| 2026-05-11 | Phase A를 A1/A2/A3로 분해 + 1주차(A2, 5/11~5/17) 멤버별 일자별 adapter 작업 상세화 + 1주차 핵심 산출물 체크리스트·의존성 그래프·PR 흐름 추가 | schemas/domain/application 완료 상태 반영. adapter 단계로 진입하며 클린아키텍처 의존성 순서(domain → application → adapter → composition)에 맞춰 phase 재정렬. 황대원의 frontend 공통 베이스(Tailwind/shadcn, 색상 토큰)는 Phase B(5/20~)로 이연. |
