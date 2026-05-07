# 클린 아키텍처 전체 설계서

- **작성일**: 2026-05-05
- **작성자**: 황대원 (조장)
- **Status**: Draft — 팀 리뷰 후 Accepted 전환
- **참조**: `class_diagram_resolution_proposal.md` (확정), `architecture.md`, `MONOREPO_STRUCTURE.md`

---

## 1. 설계 원칙

### 1.1 Clean Architecture 핵심 규칙

| 규칙 | 설명 |
|------|------|
| **의존성 방향** | 바깥 → 안쪽만 허용. Domain은 어떤 프레임워크도 모른다 |
| **의존성 역전 (DIP)** | 안쪽이 Port(인터페이스)를 정의하고, 바깥이 Adapter(구현체)를 제공한다 |
| **경계 횡단** | 계층 간 데이터 전달은 DTO 또는 도메인 엔티티로만 한다. ORM 모델이 도메인을 넘지 않는다 |
| **테스트 독립성** | Domain과 Application은 외부 시스템 없이 단위 테스트 가능 |

### 1.2 기존 프로젝트 원칙 통합

| 원칙 | 출처 | Clean Architecture 매핑 |
|------|------|------------------------|
| SSOT | 교차분석 확정 | `packages/common-schemas/`가 공유 Entity·VO·Enum의 단일 정의 |
| 도메인 소유권 | 교차분석 확정 | 각 모듈 `domain/ports/`에서 ABC를 정의, 소유 모듈이 인터페이스를 결정 |
| 합집합 확장 | 교차분석 확정 | SSOT 엔티티에 Optional 필드로 합집합 반영 |
| import 규칙 | ADR-0001 | `services/* → modules/* → packages/*` (Clean Architecture 의존성 방향과 일치) |

---

## 2. 계층 매핑 — Clean Architecture × 모노레포

### 2.1 동심원 → 디렉토리 매핑

```
┌─────────────────────────────────────────────────────────────────────┐
│  Frameworks & Drivers (Infrastructure)                              │
│                                                                     │
│  database/                    REQ-001  SQL·Alembic·Seeds            │
│  infra/                       REQ-011  Terraform·Docker             │
│  services/frontend/           REQ-010  Next.js 14·React Flow        │
│  External APIs                         Google·Slack·Modal GPU        │
├─────────────────────────────────────────────────────────────────────┤
│  Interface Adapters                                                 │
│                                                                     │
│  services/api-server/         REQ-009  Inbound (HTTP → Use Case)   │
│  services/execution-engine/   REQ-007  Inbound (Celery → Use Case) │
│  modules/storage/             REQ-008  Outbound (Use Case → DB)    │
│  modules/*/adapters/          각 REQ   외부 SDK·프레임워크 래핑      │
├─────────────────────────────────────────────────────────────────────┤
│  Application (Use Cases)                                            │
│                                                                     │
│  modules/*/application/       REQ-002~006  유스케이스 오케스트레이션 │
│  services/execution-engine/   REQ-007      워크플로우 실행 유스케이스 │
│       src/application/                                              │
├─────────────────────────────────────────────────────────────────────┤
│  Domain (Entities)                                                  │
│                                                                     │
│  packages/common-schemas/     REQ-012  공유 Entity·VO·Enum (SSOT)  │
│  modules/*/domain/            각 REQ   모듈 전용 도메인 로직         │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 의존성 방향 규칙 (확장)

```
                    ┌──────────────────────┐
                    │ packages/            │
                    │   common-schemas/    │  ← 최내곽: 아무것도 import하지 않음
                    │   (REQ-012 SSOT)     │     (Pydantic v2만 예외 허용)
                    └──────────┬───────────┘
                               │ import
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
    modules/auth/      modules/ai-agent/   modules/doc-parser/
      domain/            domain/              domain/
      ├── ports/  ◄──── 안쪽이 인터페이스 정의
      ├── entities/
      └── services/
              │ import
              ▼
    modules/*/application/use_cases/
              │ import (Port 인터페이스만)
              ▼
    modules/*/adapters/          ← Port 구현체 제공
    modules/storage/             ← Repository 구현체 제공
              │ import
              ▼
    services/api-server/         ← DI로 조립, HTTP 라우팅
    services/execution-engine/   ← DI로 조립, Celery 디스패치
              │ import
              ▼
    database/ (SQL)
    infra/ (Terraform)
    External APIs
```

#### 금지 의존성 (위반 시 CI 실패)

| 금지 방향 | 이유 |
|-----------|------|
| `modules/*/domain/` → SQLAlchemy, FastAPI, Celery | 도메인이 프레임워크에 의존하면 안 됨 |
| `modules/*/domain/` → `modules/*/adapters/` | 안쪽이 바깥을 모른다 |
| `modules/*/application/` → 구현체 직접 import | Port 인터페이스로만 참조 |
| `packages/common-schemas/` → `modules/*` | Foundation은 독립적 |
| `modules/*` → `services/*` | 순환 의존 방지 |

---

## 3. Foundation — packages/common-schemas/ (REQ-012)

Clean Architecture의 **최내곽 원**. 모든 모듈이 공유하는 Entity·VO·Enum의 SSOT.

### 3.1 디렉토리 구조

```
packages/common-schemas/
├── python/
│   ├── common_schemas/
│   │   ├── __init__.py
│   │   ├── workflow.py             # WorkflowSchema, NodeInstance, Edge, Position
│   │   ├── node.py                 # NodeConfig
│   │   ├── agent.py                # AgentState, DraftSpec, IntentResult,
│   │   │                           # SlotFillingState, UnresolvedNode
│   │   ├── document.py             # DocumentBlock, ContentBlock, FileMeta,
│   │   │                           # SourceRef, BBox, ParserMeta, AnalysisResult
│   │   ├── security.py             # PermissionSource, PlaintextCredential
│   │   ├── validation.py           # ValidationErrorResponse, ValidationErrorItem
│   │   ├── transport.py            # SSEFrame, SessionFrame, AgentNodeFrame,
│   │   │                           # RationaleDeltaFrame, SlotFillQuestionFrame,
│   │   │                           # DraftSpecDeltaFrame, ResultFrame, ErrorFrame
│   │   ├── handoff.py              # HandoffPayload, EvaluationResult
│   │   ├── enums.py                # AgentMode, ExecutionStatus, RiskLevel, ErrorCode
│   │   └── exceptions.py           # 공유 도메인 예외 (DomainError 베이스 클래스)
│   └── pyproject.toml
├── typescript/
│   ├── src/generated/              # Python → TS 자동 생성
│   └── package.json
└── scripts/
    └── generate_ts.py              # Pydantic → TypeScript codegen
```

### 3.2 설계 규칙

- **순수 데이터 모델만**: 비즈니스 로직, I/O, 외부 호출 금지
- **의존성**: `pydantic>=2.0` + Python stdlib만 허용
- **`validate_graph()` 예외**: `WorkflowSchema.validate_graph()`는 그래프 무결성 검증이므로 엔티티 자체 검증 로직으로 허용 (Pydantic `model_validator` 활용)
- **Enum은 `str` 상속**: JSON 직렬화 호환 (`class RiskLevel(str, Enum)`)

---

## 4. Domain Modules — 표준 내부 구조

### 4.1 모듈 내부 표준 템플릿

모든 도메인 모듈(`modules/auth/`, `modules/ai-agent/` 등)은 아래 3계층 구조를 따른다.

```
modules/{module_name}/
├── __init__.py                     # 모듈 public API (re-export)
├── domain/                         # ① 최내곽 — 순수 비즈니스 로직
│   ├── __init__.py
│   ├── entities/                   # 모듈 전용 도메인 엔티티
│   │   └── __init__.py
│   ├── value_objects/              # 모듈 전용 VO
│   │   └── __init__.py
│   ├── services/                   # 도메인 서비스 (순수 비즈니스 규칙)
│   │   └── __init__.py
│   └── ports/                      # 인터페이스 정의 (ABC)
│       └── __init__.py             # — Repository ABC, 외부 서비스 Port
├── application/                    # ② 유스케이스 — 도메인 조합 로직
│   ├── __init__.py
│   └── use_cases/                  # 각 유스케이스 = 1 클래스, execute() 메서드
│       └── __init__.py
├── adapters/                       # ③ 어댑터 — 외부 시스템 연동
│   ├── __init__.py
│   └── ...                         # SDK 래핑, 프레임워크 통합
└── tests/
    ├── unit/
    │   ├── domain/                 # 도메인 순수 테스트 (mock 불필요)
    │   └── application/            # 유스케이스 테스트 (Port mock)
    └── integration/
        └── adapters/               # 어댑터 통합 테스트
```

### 4.2 계층 간 의존성 규칙 (모듈 내부)

```
domain/
  ├── entities/     ← common-schemas import만 허용
  ├── value_objects/← common-schemas import만 허용
  ├── services/     ← entities + value_objects + ports + common-schemas
  └── ports/        ← entities + value_objects + common-schemas (ABC만 정의)

application/
  └── use_cases/    ← domain/* + common-schemas (ports를 통해서만 외부 접근)

adapters/
  └── ...           ← domain/ports 구현 + 외부 라이브러리 자유 사용
```

---

## 5. 모듈별 상세 설계

### 5.1 REQ-002 Auth-Security

```
modules/auth/
├── __init__.py
├── domain/
│   ├── entities/
│   │   ├── session.py                  # Session (도메인 모델, ORM 아님)
│   │   └── oauth_connection.py         # OAuthConnection
│   ├── value_objects/
│   │   └── token_pair.py               # AccessToken + RefreshToken 쌍
│   ├── services/
│   │   ├── permission_resolver.py      # PermissionSource 결정 로직
│   │   │                               #   입력: user_id, role, department
│   │   │                               #   출력: PermissionSource (REQ-012)
│   │   └── credential_injection.py     # CredentialInjectionService
│   │                                   #   NodeInstance.credential_id → PlaintextCredential
│   │                                   #   메모리 내 복호화, 사용 후 wipe()
│   └── ports/
│       ├── session_repository.py       # SessionRepository (ABC)
│       │   # create(user_id, hash) → Session
│       │   # find_by_hash(hash) → Session
│       │   # revoke(session_id) → None
│       │   # revoke_all_for_user(user_id) → int
│       ├── oauth_repository.py         # OAuthConnectionRepository (ABC)
│       │   # create(user_id, service, tokens) → OAuthConnection
│       │   # get_by_credential_id(cid) → OAuthConnection
│       │   # get_active_for_user(uid, svc) → OAuthConnection
│       │   # update_tokens(cid, new_tokens) → None
│       │   # revoke(cid) → None
│       └── cipher_port.py              # CipherPort (ABC)
│           # encrypt(plaintext: bytes) → bytes
│           # decrypt(ciphertext: bytes) → bytes
├── application/
│   └── use_cases/
│       ├── authenticate.py             # AuthenticateUseCase
│       │   # Google OAuth callback → Session 생성 → JWT 발급
│       ├── issue_token.py              # IssueTokenUseCase
│       │   # session_hash → AccessToken + RefreshToken
│       ├── refresh_token.py            # RefreshTokenUseCase
│       │   # refresh_token → new AccessToken
│       └── inject_credential.py        # InjectCredentialUseCase
│           # credential_id → PlaintextCredential (복호화)
│           # 실행 후 자동 wipe()
└── adapters/
    ├── google_oauth.py                 # GoogleOAuthAdapter
    │   # authorization_url() → str
    │   # exchange_code(code) → tokens
    ├── jwt_adapter.py                  # JWTAdapter (PyJWT 래핑)
    │   # encode(payload) → token_str
    │   # decode(token_str) → payload
    ├── cipher/
    │   ├── base_cipher.py              # BaseCipher (CipherPort 구현 베이스)
    │   ├── aesgcm_cipher.py            # AESGCMCipher (CipherPort 구현)
    │   └── fernet_cipher.py            # FernetCipher (CipherPort 구현)
    └── middleware.py                   # FastAPI AuthMiddleware
        # Request → JWT 검증 → PermissionSource 주입
```

**핵심 의존성 역전:**
- `CredentialInjectionService`는 `CipherPort` ABC에만 의존
- `AESGCMCipher` / `FernetCipher`는 `adapters/`에서 `CipherPort`를 구현
- 어떤 cipher를 쓸지는 DI 시점에 결정 (REQ-001 DB 계층이 아닌 REQ-002가 소유 — H-2 확정)

---

### 5.2 REQ-003 Nodes-Graph

```
modules/nodes-graph/
├── __init__.py
├── domain/
│   ├── entities/
│   │   └── node_definition.py          # NodeDefinition
│   │       # NodeConfig(REQ-012) 확장
│   │       # 추가 필드: service_type, required_connections (H-4 확정)
│   │       # 54종 노드 정의의 도메인 표현
│   ├── services/
│   │   ├── graph_validator.py          # GraphValidator (SchemaValidation)
│   │   │   # WorkflowSchema → ValidationErrorResponse
│   │   │   # 검증: 사이클 감지, 고립 노드, 타입 불일치, 필수 연결
│   │   └── graph_serializer.py         # GraphSerializer
│   │       # WorkflowSchema ↔ 직렬화 형식 변환
│   └── ports/
│       └── node_definition_repository.py   # NodeDefinitionRepository (ABC)
│           # get_by_id(node_id) → NodeDefinition
│           # list_all() → list[NodeDefinition]
│           # search_by_embedding(query, k) → list[NodeDefinition]
│           # upsert(node_def) → NodeDefinition
├── application/
│   └── use_cases/
│       ├── validate_graph.py           # ValidateGraphUseCase
│       │   # WorkflowSchema → ValidationErrorResponse
│       └── search_nodes.py             # SearchNodesUseCase
│           # query → list[NodeDefinition] (임베딩 기반)
└── adapters/
    └── tool_to_node_wrapper.py         # ToolToNodeWrapper
        # REQ-005 BaseTool → REQ-003 NodeDefinition 변환
        # risk_level 매핑 (RiskLevel Enum, M-8 확정)
```

**핵심 결정 (교차분석 확정 반영):**
- WorkflowSchema, NodeInstance, Edge → 자체 정의 삭제, REQ-012 import (H-1)
- NodeDefinition은 NodeConfig(REQ-012)를 확장하되 모듈 전용 엔티티로 유지 (H-4)

---

### 5.3 REQ-004 AI Agent

```
modules/ai-agent/
├── __init__.py
├── domain/
│   ├── entities/
│   │   ├── memory_entry.py             # MemoryEntry
│   │   │   # user_id, memory_type, content, source_session_id (M-10)
│   │   │   # ORM 전용 필드(confidence, usage_count) 미포함
│   │   └── correction_pattern.py       # CorrectionPattern
│   │       # 에이전트 자기교정 패턴
│   ├── value_objects/
│   │   └── evaluation_result.py        # EvaluationResult
│   │       # score, pass_flag, reason, feedback
│   ├── services/
│   │   ├── intent_analyzer.py          # IntentAnalyzerService
│   │   │   # messages → IntentResult (clarify/draft/refine/propose)
│   │   │   # importance_score 계산 담당 (M-7 확정)
│   │   ├── qa_evaluator.py             # QAEvaluatorService
│   │   │   # LLM-as-a-Judge, score ≥ 8 통과
│   │   │   # WorkflowSchema → EvaluationResult
│   │   ├── drafter.py                  # DrafterService
│   │   │   # IntentResult + NodeCandidates → WorkflowSchema 초안
│   │   └── onboarding_consultant.py    # OnboardingConsultant (Skills Wizard)
│   │       # 신규 사용자 온보딩 대화 관리
│   └── ports/
│       ├── agent_memory_repository.py  # AgentMemoryRepository (ABC)
│       │   # save(entry) → MemoryEntry
│       │   # search(user_id, query, k) → list[MemoryEntry]
│       │   # delete(memory_id) → None
│       ├── node_registry.py            # NodeRegistry (Facade, M-11 확정)
│       │   # NodeDefinitionRepository를 주입받는 어댑터
│       │   # search(query, k) → list[NodeConfig]
│       │   # get_schema(node_type) → dict
│       └── llm_port.py                 # LLMPort (ABC)
│           # generate(messages, tools?) → response
│           # embed(text) → vector
├── application/
│   └── use_cases/
│       ├── compose_workflow.py         # ComposeWorkflowUseCase
│       │   # 메인 LangGraph 오케스트레이션 진입점
│       │   # AgentState 관리, 13 노드 그래프 실행
│       │   # turn_count ≤ 25 제한 (H-9)
│       └── onboarding.py              # OnboardingUseCase
│           # Skills Wizard 세션 관리
└── adapters/
    ├── langgraph/
    │   ├── graph_builder.py            # LangGraph StateGraph 정의
    │   │   # 13개 AgentNode 연결: security → onboarding → intent
    │   │   #   → retriever → drafter ↔ validator (max 3) → qa → propose/promote
    │   ├── nodes/                      # 13개 AgentNode 구현
    │   │   ├── security_node.py
    │   │   ├── onboarding_node.py
    │   │   ├── intent_node.py
    │   │   ├── retriever_node.py
    │   │   ├── drafter_node.py
    │   │   ├── validator_node.py
    │   │   ├── qa_evaluator_node.py
    │   │   ├── propose_node.py
    │   │   └── promote_node.py
    │   └── checkpointer.py            # LangGraph Checkpointer 설정
    │       # thread_id = f"{user_id}:{session_id}"
    └── llm/
        └── modal_adapter.py           # Modal L4 GPU LLM 클라이언트
            # Gemma 4 + BGE-M3 호출
```

**핵심 의존성 흐름:**
```
domain/services/intent_analyzer.py
    → ports/llm_port.py (ABC)           # LLM 호출은 Port를 통해
    → common_schemas.agent (IntentResult)  # SSOT 타입 사용

adapters/langgraph/nodes/intent_node.py
    → domain/services/intent_analyzer.py  # 도메인 서비스 호출
    → (LangGraph 프레임워크 의존)          # 어댑터에서만 프레임워크 사용
```

**LangGraph 위치 결정 근거:**
- LangGraph는 프레임워크다 → `adapters/`에 위치
- 비즈니스 로직(의도 분석, 품질 평가)은 `domain/services/`에 순수 함수로 분리
- 각 LangGraph 노드는 도메인 서비스를 호출하는 얇은 래퍼

---

### 5.4 REQ-005 Toolset

```
modules/toolset/
├── __init__.py
├── domain/
│   ├── entities/
│   │   └── base_tool.py                # BaseTool (ABC)
│   │       # tool_id, name, description, risk_level: RiskLevel (M-8)
│   │       # input_schema, output_schema
│   │       # @abstractmethod run(params, credential) → result
│   ├── services/
│   │   └── runtime_validator.py        # RuntimeValidator
│   │       # 도구 실행 시점 I/O 스키마 검증 (per-tool, 데이터 타입 검증)
│   │       # ≠ QAEvaluatorService (워크플로우 품질 평가, M-9 확정)
│   └── ports/
│       ├── tool_registry.py            # ToolRegistry (ABC)
│       │   # get_tool(tool_id) → BaseTool
│       │   # list_tools() → list[BaseTool]
│       └── secure_connector_port.py    # SecureConnectorPort (ABC)
│           # acquire_credential(credential_id, service) → credential_data
│           # release_credential(credential_id) → None
├── application/
│   └── use_cases/
│       ├── execute_tool.py             # ExecuteToolUseCase
│       │   # tool_id + params + credential → validated result
│       │   # 1. RuntimeValidator.validate_input(params)
│       │   # 2. tool.run(params, credential)
│       │   # 3. RuntimeValidator.validate_output(result)
│       └── register_tool.py            # RegisterToolUseCase
│           # BaseTool 등록/갱신
└── adapters/
    ├── tools/                          # 8개 Tool 구현 (BaseTool 상속)
    │   ├── google_drive_tool.py
    │   ├── gmail_tool.py
    │   ├── slack_tool.py
    │   ├── google_calendar_tool.py
    │   ├── google_sheets_tool.py
    │   ├── webhook_tool.py
    │   ├── http_request_tool.py
    │   └── llm_tool.py
    ├── secure_connector.py             # SecureConnector 구현체
    │   # OAuth 토큰 관리, Credential 주입
    └── state_manager.py                # StateManager
        # 도구 실행 상태 추적
```

---

### 5.5 REQ-006 Doc Parser

```
modules/doc-parser/
├── __init__.py
├── domain/
│   ├── entities/
│   │   └── parser_meta.py              # ParserMeta
│   │       # parser_name, parser_version, config
│   ├── services/
│   │   ├── chunking_service.py         # ChunkingService
│   │   │   # ContentBlock[] → Chunk[] (토큰 기반 분할)
│   │   │   # importance_score=None (REQ-004가 나중에 채움, M-7 확정)
│   │   └── quality_gate.py             # QualityGate
│   │       # 파싱 품질 검증 (빈 블록 제거, 최소 토큰 수 등)
│   └── ports/
│       └── parser_port.py              # ParserPort (ABC)
│           # parse(file_bytes, file_meta) → list[ContentBlock]
│           # supported_types() → list[str]
├── application/
│   └── use_cases/
│       ├── parse_document.py           # ParseDocumentUseCase
│       │   # file → ParserPort.parse() → QualityGate → DocumentBlock
│       └── extract_chunks.py           # ExtractChunksUseCase
│           # DocumentBlock → ChunkingService → Chunk[]
└── adapters/
    └── parsers/                        # 7개 ParserPort 구현체
        ├── pdf_parser.py               # PyMuPDF / pdfplumber
        ├── docx_parser.py              # python-docx
        ├── xlsx_parser.py              # openpyxl
        ├── csv_parser.py               # csv stdlib
        ├── pptx_parser.py              # python-pptx
        ├── hwp_parser.py               # pyhwp / olefile
        └── hwpx_parser.py              # lxml (OOXML)
```

---

### 5.6 REQ-007 Execution Engine

실행 엔진은 `services/`에 위치하지만, 내부적으로 Clean Architecture를 따른다.

```
services/execution-engine/
├── src/
│   ├── domain/
│   │   ├── services/
│   │   │   └── topological_scheduler.py    # TopologicalScheduler (M-1 확정)
│   │   │       # Kahn's algorithm으로 노드 실행 순서 결정
│   │   │       # WorkflowSchema → list[list[NodeInstance]] (병렬 가능 그룹)
│   │   └── ports/
│   │       ├── workflow_repository.py      # WorkflowRepositoryPort (ABC)
│   │       │   # get(workflow_id) → WorkflowSchema
│   │       ├── node_executor_port.py       # NodeExecutorPort (ABC)
│   │       │   # execute(node_instance, credentials) → result
│   │       └── task_queue_port.py          # TaskQueuePort (ABC)
│   │           # enqueue(task) → task_id
│   │           # get_status(task_id) → status
│   ├── application/
│   │   └── use_cases/
│   │       ├── execute_workflow.py         # ExecuteWorkflowUseCase
│   │       │   # workflow_id → 전체 실행 오케스트레이션
│   │       │   # 1. WorkflowRepository.get(workflow_id)
│   │       │   # 2. sha256 무결성 검증 (H-10)
│   │       │   # 3. TopologicalScheduler.schedule(workflow)
│   │       │   # 4. 노드별 TaskQueue.enqueue()
│   │       │   # 5. node_logs flush
│   │       └── dispatch_node.py            # DispatchNodeUseCase
│   │           # 단일 노드 실행 + 결과 기록
│   └── adapters/
│       ├── celery_adapter.py               # Celery TaskQueue 구현체
│       │   # execute_workflow.delay(workflow_id)
│       │   # Celery 2-tier worker (high/low priority)
│       ├── sandbox_executor.py             # SandboxExecutor
│       │   # 노드 실행 격리 (subprocess / container)
│       └── langgraph_dispatcher.py         # LangGraph Agent WS 디스패처
├── tests/
├── Dockerfile
└── pyproject.toml
```

**REQ-004 → REQ-007 핸드오프 (M-5 확정: 비동기):**
```
REQ-004 QAEvaluator (score ≥ 8)
    → WorkflowRepository.save(workflow)         # modules/storage 경유
    → workflow_id 반환 (SSE로 프론트엔드에 전달)

REQ-009 API Server (사용자 "실행" 클릭)
    → POST /api/v1/workflows/{id}/execute
    → Celery: execute_workflow.delay(workflow_id)

REQ-007 Celery Worker
    → ExecuteWorkflowUseCase.execute(workflow_id)
```

---

## 6. Persistence Adapter — modules/storage/ (REQ-008)

Clean Architecture에서 **Outbound Adapter** 역할. 다른 모듈이 정의한 Repository ABC를 구현한다.

### 6.1 디렉토리 구조

```
modules/storage/
├── __init__.py
├── orm/                                # SQLAlchemy ORM 모델 (DB 테이블 1:1)
│   ├── __init__.py
│   ├── user_model.py
│   ├── workflow_model.py
│   ├── node_instance_model.py
│   ├── execution_model.py
│   ├── session_model.py                # ChatSessionModel (REQ-001)
│   ├── oauth_connection_model.py
│   ├── credential_model.py
│   ├── node_definition_model.py        # 54종 노드 + embedding vector(768)
│   ├── agent_memory_model.py           # user_id, memory_type (M-10 필드명 통일)
│   ├── document_model.py
│   ├── skill_model.py
│   ├── approval_model.py
│   ├── notification_model.py
│   └── audit_log_model.py
├── repositories/                       # Repository ABC 구현체
│   ├── __init__.py
│   ├── session_repository.py           # → auth/domain/ports/SessionRepository
│   ├── oauth_repository.py             # → auth/domain/ports/OAuthConnectionRepository
│   ├── workflow_repository.py          # → 자체 + execution-engine Port
│   ├── skill_repository.py             # → 자체 (마켓플레이스)
│   ├── node_definition_repository.py   # → nodes-graph/domain/ports/NodeDefinitionRepository
│   ├── agent_memory_repository.py      # → ai-agent/domain/ports/AgentMemoryRepository
│   ├── document_repository.py          # → 자체
│   └── execution_repository.py         # → 자체
├── mappers/                            # ORM ↔ 도메인 엔티티 변환
│   ├── __init__.py
│   ├── session_mapper.py               # ChatSessionModel ↔ Session
│   ├── workflow_mapper.py              # WorkflowORM ↔ WorkflowSchema
│   └── ...                             # 각 엔티티별 매퍼
├── marketplace/                        # 마켓플레이스 도메인 (REQ-008 고유)
│   ├── domain/
│   │   ├── skill_lifecycle.py          # 5-state machine (draft→review→approved→published→archived)
│   │   └── approval_workflow.py        # 승인 워크플로우
│   └── application/
│       └── use_cases/
│           ├── publish_skill.py        # PublishSkillUseCase
│           ├── search_skills.py        # SearchSkillsUseCase (하이브리드 검색)
│           └── approve_skill.py        # ApproveSkillUseCase
└── tests/
```

### 6.2 ORM ↔ 도메인 매핑 원칙

```python
# modules/storage/mappers/session_mapper.py 예시

class SessionMapper:
    @staticmethod
    def to_domain(orm: ChatSessionModel) -> Session:
        """ORM 모델 → 도메인 엔티티. DB 계층 정보를 도메인 형태로 변환."""
        return Session(
            session_id=orm.id,
            user_id=orm.user_id,
            hash=orm.session_hash,
            created_at=orm.created_at,
            is_revoked=orm.is_revoked,
        )

    @staticmethod
    def to_orm(entity: Session) -> ChatSessionModel:
        """도메인 엔티티 → ORM 모델. 저장 시 사용."""
        return ChatSessionModel(
            id=entity.session_id,
            user_id=entity.user_id,
            session_hash=entity.hash,
            is_revoked=entity.is_revoked,
        )
```

**규칙:**
- ORM 모델은 `modules/storage/orm/` 밖으로 절대 노출하지 않는다
- Repository 구현체는 항상 도메인 엔티티를 반환한다
- 매퍼는 양방향(to_domain / to_orm) 정적 메서드를 제공한다

---

## 7. Inbound Adapters — services/

### 7.1 REQ-009 API Server

```
services/api-server/
├── app/
│   ├── main.py                         # FastAPI 엔트리포인트
│   │   # CORS, 미들웨어, 라우터 등록
│   ├── routers/                        # Inbound Adapter (HTTP → Use Case)
│   │   ├── auth.py                     # /api/v1/auth/*
│   │   ├── workflows.py               # /api/v1/workflows/*
│   │   ├── ai.py                       # /api/v1/ai/*
│   │   ├── executions.py              # /api/v1/executions/*
│   │   ├── skills.py                   # /api/v1/skills/*
│   │   ├── marketplace.py             # /api/v1/marketplace/*
│   │   ├── documents.py               # /api/v1/documents/*
│   │   ├── nodes.py                    # /api/v1/nodes/*
│   │   ├── tools.py                    # /api/v1/tools/*
│   │   ├── users.py                    # /api/v1/users/*
│   │   ├── approvals.py               # /api/v1/approvals/*
│   │   ├── notifications.py           # /api/v1/notifications/*
│   │   └── admin.py                    # /api/v1/admin/*
│   ├── dependencies/                   # ★ DI 컨테이너 — 전체 조립 지점
│   │   ├── __init__.py
│   │   ├── database.py                # AsyncSession provider
│   │   ├── auth.py                    # Auth 관련 DI
│   │   ├── repositories.py           # Repository 구현체 주입
│   │   ├── use_cases.py              # Use Case 주입
│   │   └── tools.py                   # Tool 관련 DI
│   ├── middleware/
│   │   ├── auth.py                    # JWT 검증 → PermissionSource 주입
│   │   ├── cors.py                    # CORS 설정
│   │   ├── logging.py                 # 요청 로깅
│   │   └── error_handler.py           # DomainError → HTTP Response 매핑
│   └── sse/
│       └── handler.py                 # SSE 스트리밍 핸들러
│           # AgentState 변경 → SSEFrame 직렬화 → 클라이언트 전송
├── tests/
├── Dockerfile
└── pyproject.toml
```

**라우터 설계 원칙:**
- 라우터는 **얇다**: HTTP 파싱 → Use Case 호출 → HTTP 응답 변환
- 비즈니스 로직 금지 (if/else 분기도 Use Case로 위임)
- `Depends()`로 Use Case를 주입받아 `execute()` 호출

```python
# services/api-server/app/routers/workflows.py 예시

@router.post("/", response_model=WorkflowResponse)
async def create_workflow(
    body: CreateWorkflowRequest,
    permission: PermissionSource = Depends(get_permission_source),
    use_case: SaveWorkflowUseCase = Depends(get_save_workflow_use_case),
):
    workflow = await use_case.execute(
        name=body.name,
        nodes=body.nodes,
        edges=body.edges,
        owner=permission,
    )
    return WorkflowResponse.from_domain(workflow)
```

### 7.2 REQ-010 Frontend

프론트엔드는 Python Clean Architecture와 별도 — Next.js 자체 아키텍처를 따른다.

```
services/frontend/
├── src/
│   ├── app/                            # Next.js 14 App Router
│   │   ├── (auth)/                     # 인증 그룹 라우트
│   │   ├── (dashboard)/                # 대시보드 그룹 라우트
│   │   │   ├── workflows/             # 워크플로우 관리
│   │   │   ├── marketplace/           # 마켓플레이스
│   │   │   └── settings/              # 설정
│   │   └── layout.tsx
│   ├── components/                     # React 컴포넌트
│   │   ├── canvas/                    # React Flow 기반 워크플로우 캔버스
│   │   │   ├── Canvas.tsx
│   │   │   ├── NodePanel.tsx
│   │   │   └── EdgeRenderer.tsx
│   │   ├── chat/                      # AI Agent 채팅 패널
│   │   │   ├── ChatPanel.tsx
│   │   │   └── MessageBubble.tsx
│   │   ├── execution/                 # 실행 결과 뷰어
│   │   │   ├── ResultDrawer.tsx
│   │   │   └── NodeLogViewer.tsx
│   │   └── common/                    # 공통 컴포넌트
│   ├── stores/                         # Zustand 상태 관리
│   │   ├── workflow-store.ts          # 워크플로우 상태
│   │   ├── agent-store.ts             # AI Agent 대화 상태
│   │   ├── execution-store.ts         # 실행 상태
│   │   └── auth-store.ts             # 인증 상태
│   ├── services/                       # API 클라이언트 (Adapter 역할)
│   │   ├── api-client.ts              # Axios/fetch 래핑
│   │   └── sse-parser.ts             # SSE 이벤트 파서
│   └── types/                          # TypeScript 타입 (REQ-012에서 생성)
├── public/
├── tests/
├── Dockerfile
├── package.json
└── tsconfig.json
```

---

## 8. Infrastructure — database/ + infra/ (REQ-001, 011)

### 8.1 database/ (REQ-001)

순수 SQL 계층. Python 코드 의존 없음.

```
database/
├── schemas/                            # DDL (15개 SQL 파일)
│   ├── 001_core.sql                   # users, workflows, executions
│   ├── ...
│   └── 015_node_logs_extended.sql
├── migrations/                         # Alembic
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
├── seeds/                              # 초기 데이터
│   └── node_definitions.sql           # 54종 노드 정의
├── scripts/                            # DB 유틸리티
└── tests/                              # SQL 테스트 (pgTAP 등)
```

### 8.2 infra/ (REQ-011)

```
infra/
├── terraform/
│   ├── modules/                        # 재사용 가능 Terraform 모듈
│   │   ├── cloud-run/                 # 4개 서비스 (api, frontend, worker, beat)
│   │   ├── cloud-sql/                 # PostgreSQL 16
│   │   ├── memorystore/               # Redis 7
│   │   ├── gcs/                       # 5개 버킷
│   │   ├── secret-manager/            # 9개 시크릿
│   │   └── networking/                # VPC + Serverless Connector
│   └── envs/
│       ├── staging/
│       └── production/
└── docker/
    └── docker-compose.dev.yml         # 로컬 개발 (PostgreSQL + Redis)
```

---

## 9. Dependency Injection 전략

### 9.1 조립 지점 (Composition Root)

DI 조립은 **애플리케이션 진입점**에서만 수행한다:
- `services/api-server/app/dependencies/` — FastAPI `Depends()`
- `services/execution-engine/src/dependencies/` — Celery worker 초기화

**도메인과 애플리케이션 계층은 DI 프레임워크를 모른다.**

### 9.2 DI 흐름 예시

```
┌─ services/api-server/app/dependencies/ ─────────────────────────┐
│                                                                  │
│  AsyncSession ──────────────────────────────────────┐            │
│       │                                             │            │
│       ▼                                             ▼            │
│  PostgresSessionRepo ─────────┐    AESGCMCipher ────┐           │
│  (modules/storage)            │    (modules/auth)    │           │
│       │ implements            │         │ implements │           │
│       ▼                       │         ▼            │           │
│  SessionRepository (ABC) ─────┤    CipherPort (ABC) ─┤          │
│  (modules/auth/domain/ports)  │    (modules/auth)     │          │
│       │                       │         │             │          │
│       ▼                       ▼         ▼             │          │
│  AuthenticateUseCase(session_repo, cipher_port) ──────┘          │
│  (modules/auth/application)                                      │
│       │                                                          │
│       ▼                                                          │
│  Router.authenticate(use_case=Depends(...))                      │
│  (services/api-server/app/routers)                               │
└──────────────────────────────────────────────────────────────────┘
```

### 9.3 코드 예시

```python
# services/api-server/app/dependencies/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

engine = create_async_engine(os.getenv("DATABASE_URL"))

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(engine) as session:
        yield session


# services/api-server/app/dependencies/repositories.py
from modules.auth.domain.ports.session_repository import SessionRepository
from modules.storage.repositories.session_repository import PostgresSessionRepository

def get_session_repository(
    db: AsyncSession = Depends(get_db),
) -> SessionRepository:
    return PostgresSessionRepository(db)


# services/api-server/app/dependencies/use_cases.py
from modules.auth.application.use_cases.authenticate import AuthenticateUseCase

def get_authenticate_use_case(
    session_repo: SessionRepository = Depends(get_session_repository),
    oauth: GoogleOAuthAdapter = Depends(get_google_oauth),
    jwt: JWTAdapter = Depends(get_jwt_adapter),
) -> AuthenticateUseCase:
    return AuthenticateUseCase(
        session_repo=session_repo,
        oauth_adapter=oauth,
        jwt_adapter=jwt,
    )
```

---

## 10. 에러 처리 전략

### 10.1 도메인 예외 계층

```python
# packages/common-schemas/python/common_schemas/exceptions.py

class DomainError(Exception):
    """모든 도메인 예외의 베이스"""
    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message

class ValidationError(DomainError): ...
class AuthorizationError(DomainError): ...
class NotFoundError(DomainError): ...
class ConflictError(DomainError): ...
class IntegrityError(DomainError): ...
```

### 10.2 계층별 예외 흐름

```
Domain Service → DomainError 발생
    ↓
Use Case → DomainError 전파 (필요 시 컨텍스트 추가)
    ↓
Router → DomainError 캐치 없음 (middleware로 위임)
    ↓
ErrorHandler Middleware → DomainError → HTTP Response 매핑
    ValidationError   → 422
    AuthorizationError → 403
    NotFoundError      → 404
    ConflictError      → 409
    IntegrityError     → 500
    DomainError        → 400 (기본)
```

---

## 11. 데이터 흐름 — Clean Architecture 경계 표시

### 11.1 시나리오: "주간 보고서를 요약해서 슬랙으로"

```
[1] Frontend (React)
    │ POST /api/v1/ai/compose?stream=true
    │ body: { message: "주간 보고서를 요약해서 슬랙으로" }
    ▼
[2] API Server — Router (Inbound Adapter)
    │ routers/ai.py → JWT 검증 → PermissionSource 주입
    │ Depends(get_compose_workflow_use_case)
    ▼
[3] AI Agent — Use Case (Application Layer)
    │ ComposeWorkflowUseCase.execute(message, permission)
    │   → AgentState 생성 (REQ-012 SSOT)
    │   → LangGraph 그래프 실행 시작
    ▼
[4] AI Agent — LangGraph (Adapter Layer)
    │ adapters/langgraph/graph_builder.py
    │ 각 노드는 Domain Service를 호출:
    │
    │ ┌── security_node ──────────────────────────────────┐
    │ │   domain/services/credential_injection.py (REQ-002)│
    │ │   PermissionSource.risk_ceiling 검증               │
    │ └──────────────────────────────────────────────────────┘
    │ ┌── intent_node ────────────────────────────────────┐
    │ │   domain/services/intent_analyzer.py               │
    │ │   → LLMPort.generate() (Port, ABC)                │
    │ │   → IntentResult (REQ-012 SSOT)                   │
    │ └──────────────────────────────────────────────────────┘
    │ ┌── retriever_node ─────────────────────────────────┐
    │ │   domain/ports/node_registry.py                    │
    │ │   → NodeDefinitionRepository (REQ-003 ABC)        │
    │ │   → list[NodeConfig] (REQ-012 SSOT)               │
    │ └──────────────────────────────────────────────────────┘
    │ ┌── drafter_node ───────────────────────────────────┐
    │ │   domain/services/drafter.py                       │
    │ │   → WorkflowSchema 초안 생성 (REQ-012 SSOT)       │
    │ └──────────────────────────────────────────────────────┘
    │ ┌── validator_node (max 3회) ───────────────────────┐
    │ │   GraphValidator (REQ-003 Domain Service)          │
    │ │   → ValidationErrorResponse (REQ-012)             │
    │ └──────────────────────────────────────────────────────┘
    │ ┌── qa_evaluator_node ──────────────────────────────┐
    │ │   domain/services/qa_evaluator.py                  │
    │ │   → EvaluationResult (score ≥ 8 통과)             │
    │ └──────────────────────────────────────────────────────┘
    │
    │ [SSE 스트리밍] 각 노드 실행 시 SSEFrame 전송
    │   SessionFrame → AgentNodeFrame → RationaleDeltaFrame
    │   → DraftSpecDeltaFrame → ResultFrame
    ▼
[5] API Server — SSE Handler (Adapter)
    │ AgentState → SSEFrame 직렬화 → text/event-stream
    ▼
[6] Frontend — SSE Parser
    │ SSEFrame → Zustand store 업데이트
    │ Canvas에 WorkflowSchema 렌더링
    ▼
[7] 사용자: [Save] 클릭
    │ POST /api/v1/workflows
    ▼
[8] API Server — Router → Use Case
    │ SaveWorkflowUseCase.execute(workflow)
    │   → WorkflowRepository.save() (Port, ABC)
    │   → modules/storage (Outbound Adapter) → DB 저장
    ▼
[9] 사용자: [Execute] 클릭
    │ POST /api/v1/workflows/{id}/execute
    ▼
[10] API Server — Router → Celery enqueue
    │ execute_workflow.delay(workflow_id)
    │ ──── REQ-004 → REQ-007 비동기 핸드오프 ────
    ▼
[11] Execution Engine — Celery Worker (Inbound Adapter)
    │ ExecuteWorkflowUseCase.execute(workflow_id)
    │   1. WorkflowRepository.get(workflow_id)
    │   2. sha256 무결성 검증
    │   3. TopologicalScheduler.schedule(workflow)
    │   4. 노드별: DispatchNodeUseCase.execute(node)
    │      → CredentialInjectionService (REQ-002)
    │      → ExecuteToolUseCase (REQ-005)
    │      → node_logs flush (REQ-001)
    ▼
[12] Frontend — Polling
    │ GET /api/v1/executions/{exec_id}
    │ ResultDrawer 렌더
```

---

## 12. 테스트 전략

### 12.1 계층별 테스트 범위

| 계층 | 테스트 종류 | 외부 의존성 | 도구 |
|------|-----------|-----------|------|
| Domain (entities, services) | Unit | 없음 (순수 Python) | pytest |
| Application (use cases) | Unit | Port mock (unittest.mock) | pytest + mock |
| Adapters | Integration | 실제 외부 시스템 | pytest + testcontainers |
| API Server (routers) | E2E | 전체 스택 | pytest + httpx + testcontainers |

### 12.2 테스트 디렉토리 구조

```
modules/{module}/tests/
├── conftest.py                     # 공통 fixture
├── unit/
│   ├── domain/                    # 도메인 엔티티·서비스 테스트
│   │   ├── test_entities.py       # Entity 생성·검증
│   │   └── test_services.py       # Domain Service 순수 로직
│   └── application/               # Use Case 테스트
│       └── test_use_cases.py      # Port mock 주입하여 테스트
└── integration/
    └── adapters/                   # Adapter 통합 테스트
        └── test_adapters.py        # 실제 DB/API 연동
```

### 12.3 테스트 예시

```python
# modules/auth/tests/unit/application/test_authenticate.py

class TestAuthenticateUseCase:
    def test_successful_authentication(self):
        # Arrange — Port mock
        session_repo = Mock(spec=SessionRepository)
        oauth = Mock(spec=GoogleOAuthAdapter)
        jwt = Mock(spec=JWTAdapter)

        oauth.exchange_code.return_value = {"access_token": "...", "email": "..."}
        session_repo.create.return_value = Session(session_id=uuid4(), ...)
        jwt.encode.return_value = "jwt_token_string"

        use_case = AuthenticateUseCase(session_repo, oauth, jwt)

        # Act
        result = await use_case.execute(code="auth_code_from_google")

        # Assert
        session_repo.create.assert_called_once()
        jwt.encode.assert_called_once()
        assert result.access_token == "jwt_token_string"
```

---

## 13. 전체 디렉토리 구조 (최종)

```
Workflow_Automation/
│
├── packages/
│   └── common-schemas/                     # REQ-012 SSOT (최내곽 원)
│       ├── python/
│       │   ├── common_schemas/
│       │   │   ├── __init__.py
│       │   │   ├── workflow.py             # WorkflowSchema, NodeInstance, Edge, Position
│       │   │   ├── node.py                 # NodeConfig
│       │   │   ├── agent.py                # AgentState, DraftSpec, IntentResult, ...
│       │   │   ├── document.py             # DocumentBlock, ContentBlock, FileMeta, ...
│       │   │   ├── security.py             # PermissionSource, PlaintextCredential
│       │   │   ├── validation.py           # ValidationErrorResponse, ...
│       │   │   ├── transport.py            # SSEFrame 계열
│       │   │   ├── handoff.py              # HandoffPayload, EvaluationResult
│       │   │   ├── enums.py                # AgentMode, ExecutionStatus, RiskLevel, ErrorCode
│       │   │   └── exceptions.py           # DomainError 계층
│       │   └── pyproject.toml
│       ├── typescript/
│       └── scripts/
│
├── modules/
│   ├── auth/                               # REQ-002 Auth-Security
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/
│   │   │   │   ├── session.py
│   │   │   │   └── oauth_connection.py
│   │   │   ├── value_objects/
│   │   │   │   └── token_pair.py
│   │   │   ├── services/
│   │   │   │   ├── permission_resolver.py
│   │   │   │   └── credential_injection.py
│   │   │   └── ports/
│   │   │       ├── session_repository.py
│   │   │       ├── oauth_repository.py
│   │   │       └── cipher_port.py
│   │   ├── application/
│   │   │   └── use_cases/
│   │   │       ├── authenticate.py
│   │   │       ├── issue_token.py
│   │   │       ├── refresh_token.py
│   │   │       └── inject_credential.py
│   │   ├── adapters/
│   │   │   ├── google_oauth.py
│   │   │   ├── jwt_adapter.py
│   │   │   ├── cipher/
│   │   │   │   ├── base_cipher.py
│   │   │   │   ├── aesgcm_cipher.py
│   │   │   │   └── fernet_cipher.py
│   │   │   └── middleware.py
│   │   └── tests/
│   │
│   ├── nodes-graph/                        # REQ-003 Nodes-Graph
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/
│   │   │   │   └── node_definition.py
│   │   │   ├── services/
│   │   │   │   ├── graph_validator.py
│   │   │   │   └── graph_serializer.py
│   │   │   └── ports/
│   │   │       └── node_definition_repository.py
│   │   ├── application/
│   │   │   └── use_cases/
│   │   │       ├── validate_graph.py
│   │   │       └── search_nodes.py
│   │   ├── adapters/
│   │   │   └── tool_to_node_wrapper.py
│   │   └── tests/
│   │
│   ├── ai-agent/                           # REQ-004 AI Agent
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/
│   │   │   │   ├── memory_entry.py
│   │   │   │   └── correction_pattern.py
│   │   │   ├── value_objects/
│   │   │   │   └── evaluation_result.py
│   │   │   ├── services/
│   │   │   │   ├── intent_analyzer.py
│   │   │   │   ├── qa_evaluator.py
│   │   │   │   ├── drafter.py
│   │   │   │   └── onboarding_consultant.py
│   │   │   └── ports/
│   │   │       ├── agent_memory_repository.py
│   │   │       ├── node_registry.py
│   │   │       └── llm_port.py
│   │   ├── application/
│   │   │   └── use_cases/
│   │   │       ├── compose_workflow.py
│   │   │       └── onboarding.py
│   │   ├── adapters/
│   │   │   ├── langgraph/
│   │   │   │   ├── graph_builder.py
│   │   │   │   ├── nodes/
│   │   │   │   │   ├── security_node.py
│   │   │   │   │   ├── onboarding_node.py
│   │   │   │   │   ├── intent_node.py
│   │   │   │   │   ├── retriever_node.py
│   │   │   │   │   ├── drafter_node.py
│   │   │   │   │   ├── validator_node.py
│   │   │   │   │   ├── qa_evaluator_node.py
│   │   │   │   │   ├── propose_node.py
│   │   │   │   │   └── promote_node.py
│   │   │   │   └── checkpointer.py
│   │   │   └── llm/
│   │   │       └── modal_adapter.py
│   │   └── tests/
│   │
│   ├── toolset/                            # REQ-005 Toolset
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/
│   │   │   │   └── base_tool.py
│   │   │   ├── services/
│   │   │   │   └── runtime_validator.py
│   │   │   └── ports/
│   │   │       ├── tool_registry.py
│   │   │       └── secure_connector_port.py
│   │   ├── application/
│   │   │   └── use_cases/
│   │   │       ├── execute_tool.py
│   │   │       └── register_tool.py
│   │   ├── adapters/
│   │   │   ├── tools/
│   │   │   │   ├── google_drive_tool.py
│   │   │   │   ├── gmail_tool.py
│   │   │   │   ├── slack_tool.py
│   │   │   │   ├── google_calendar_tool.py
│   │   │   │   ├── google_sheets_tool.py
│   │   │   │   ├── webhook_tool.py
│   │   │   │   ├── http_request_tool.py
│   │   │   │   └── llm_tool.py
│   │   │   ├── secure_connector.py
│   │   │   └── state_manager.py
│   │   └── tests/
│   │
│   ├── doc-parser/                         # REQ-006 Doc Parser
│   │   ├── __init__.py
│   │   ├── domain/
│   │   │   ├── entities/
│   │   │   │   └── parser_meta.py
│   │   │   ├── services/
│   │   │   │   ├── chunking_service.py
│   │   │   │   └── quality_gate.py
│   │   │   └── ports/
│   │   │       └── parser_port.py
│   │   ├── application/
│   │   │   └── use_cases/
│   │   │       ├── parse_document.py
│   │   │       └── extract_chunks.py
│   │   ├── adapters/
│   │   │   └── parsers/
│   │   │       ├── pdf_parser.py
│   │   │       ├── docx_parser.py
│   │   │       ├── xlsx_parser.py
│   │   │       ├── csv_parser.py
│   │   │       ├── pptx_parser.py
│   │   │       ├── hwp_parser.py
│   │   │       └── hwpx_parser.py
│   │   └── tests/
│   │
│   └── storage/                            # REQ-008 Persistence Adapter
│       ├── __init__.py
│       ├── orm/
│       │   ├── user_model.py
│       │   ├── workflow_model.py
│       │   ├── node_instance_model.py
│       │   ├── execution_model.py
│       │   ├── session_model.py
│       │   ├── oauth_connection_model.py
│       │   ├── credential_model.py
│       │   ├── node_definition_model.py
│       │   ├── agent_memory_model.py
│       │   ├── document_model.py
│       │   ├── skill_model.py
│       │   ├── approval_model.py
│       │   ├── notification_model.py
│       │   └── audit_log_model.py
│       ├── repositories/
│       │   ├── session_repository.py
│       │   ├── oauth_repository.py
│       │   ├── workflow_repository.py
│       │   ├── skill_repository.py
│       │   ├── node_definition_repository.py
│       │   ├── agent_memory_repository.py
│       │   ├── document_repository.py
│       │   └── execution_repository.py
│       ├── mappers/
│       │   ├── session_mapper.py
│       │   ├── workflow_mapper.py
│       │   └── ...
│       ├── marketplace/
│       │   ├── domain/
│       │   │   ├── skill_lifecycle.py
│       │   │   └── approval_workflow.py
│       │   └── application/
│       │       └── use_cases/
│       │           ├── publish_skill.py
│       │           ├── search_skills.py
│       │           └── approve_skill.py
│       └── tests/
│
├── services/
│   ├── api-server/                         # REQ-009 Inbound Adapter
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── routers/
│   │   │   │   ├── auth.py
│   │   │   │   ├── workflows.py
│   │   │   │   ├── ai.py
│   │   │   │   ├── executions.py
│   │   │   │   ├── skills.py
│   │   │   │   ├── marketplace.py
│   │   │   │   ├── documents.py
│   │   │   │   ├── nodes.py
│   │   │   │   ├── tools.py
│   │   │   │   ├── users.py
│   │   │   │   ├── approvals.py
│   │   │   │   ├── notifications.py
│   │   │   │   └── admin.py
│   │   │   ├── dependencies/
│   │   │   │   ├── database.py
│   │   │   │   ├── auth.py
│   │   │   │   ├── repositories.py
│   │   │   │   ├── use_cases.py
│   │   │   │   └── tools.py
│   │   │   ├── middleware/
│   │   │   │   ├── auth.py
│   │   │   │   ├── cors.py
│   │   │   │   ├── logging.py
│   │   │   │   └── error_handler.py
│   │   │   └── sse/
│   │   │       └── handler.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   ├── execution-engine/                   # REQ-007 Worker Adapter
│   │   ├── src/
│   │   │   ├── domain/
│   │   │   │   ├── services/
│   │   │   │   │   └── topological_scheduler.py
│   │   │   │   └── ports/
│   │   │   │       ├── workflow_repository.py
│   │   │   │       ├── node_executor_port.py
│   │   │   │       └── task_queue_port.py
│   │   │   ├── application/
│   │   │   │   └── use_cases/
│   │   │   │       ├── execute_workflow.py
│   │   │   │       └── dispatch_node.py
│   │   │   ├── adapters/
│   │   │   │   ├── celery_adapter.py
│   │   │   │   ├── sandbox_executor.py
│   │   │   │   └── langgraph_dispatcher.py
│   │   │   └── dependencies/
│   │   │       └── __init__.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── pyproject.toml
│   │
│   └── frontend/                           # REQ-010 UI Layer
│       ├── src/
│       │   ├── app/
│       │   ├── components/
│       │   │   ├── canvas/
│       │   │   ├── chat/
│       │   │   ├── execution/
│       │   │   └── common/
│       │   ├── stores/
│       │   ├── services/
│       │   └── types/
│       ├── public/
│       ├── tests/
│       ├── Dockerfile
│       ├── package.json
│       └── tsconfig.json
│
├── database/                               # REQ-001 Infrastructure
│   ├── schemas/
│   ├── migrations/
│   ├── seeds/
│   ├── scripts/
│   └── tests/
│
├── infra/                                  # REQ-011 Infrastructure
│   ├── terraform/
│   │   ├── modules/
│   │   └── envs/
│   └── docker/
│
├── docs/
│   ├── context/
│   │   ├── architecture.md
│   │   ├── clean_architecture.md           ← 본 문서
│   │   ├── decisions.md
│   │   ├── MAP.md
│   │   └── adr/
│   ├── specs/
│   └── adrs/
│
├── class_diagram/                          # 14개 .drawio 파일
├── _agent_templates/
├── scripts/
├── .github/
├── CLAUDE.md
├── MONOREPO_STRUCTURE.md
├── pyproject.toml
└── .gitignore
```

---

## 14. 모듈 간 의존성 매트릭스

### 14.1 Port ↔ Adapter 매핑 (전체)

| Port (ABC) 위치 | Port 이름 | Adapter (구현체) 위치 |
|-----------------|----------|---------------------|
| `auth/domain/ports/` | `SessionRepository` | `storage/repositories/session_repository.py` |
| `auth/domain/ports/` | `OAuthConnectionRepository` | `storage/repositories/oauth_repository.py` |
| `auth/domain/ports/` | `CipherPort` | `auth/adapters/cipher/aesgcm_cipher.py` |
| `nodes-graph/domain/ports/` | `NodeDefinitionRepository` | `storage/repositories/node_definition_repository.py` |
| `ai-agent/domain/ports/` | `AgentMemoryRepository` | `storage/repositories/agent_memory_repository.py` |
| `ai-agent/domain/ports/` | `NodeRegistry` | `ai-agent/adapters/` (내부 Facade, REQ-003 ABC 래핑) |
| `ai-agent/domain/ports/` | `LLMPort` | `ai-agent/adapters/llm/modal_adapter.py` |
| `toolset/domain/ports/` | `ToolRegistry` | `toolset/adapters/` (내부 등록) |
| `toolset/domain/ports/` | `SecureConnectorPort` | `toolset/adapters/secure_connector.py` |
| `doc-parser/domain/ports/` | `ParserPort` | `doc-parser/adapters/parsers/*.py` (7개) |
| `execution-engine/domain/ports/` | `WorkflowRepositoryPort` | `storage/repositories/workflow_repository.py` |
| `execution-engine/domain/ports/` | `NodeExecutorPort` | `execution-engine/adapters/sandbox_executor.py` |
| `execution-engine/domain/ports/` | `TaskQueuePort` | `execution-engine/adapters/celery_adapter.py` |

### 14.2 모듈 간 import 방향

```
                    common-schemas (REQ-012)
                    ┌──────┴──────┐
                    ▼             ▼
               auth (002)    nodes-graph (003)
               ┌──┴──┐          │
               ▼     ▼          ▼
          ai-agent  toolset   doc-parser
           (004)    (005)      (006)
               │      │         │
               ▼      ▼         ▼
              storage (008) ◄───┘
                    │
          ┌────────┼────────┐
          ▼                 ▼
    api-server (009)   execution-engine (007)
          │
          ▼
    frontend (010)
```

**모듈 간 import 세부 규칙:**

| From → To | 허용 범위 | 예시 |
|-----------|----------|------|
| `ai-agent` → `auth` | `domain/ports/` + `domain/services/` | CredentialInjectionService 호출 |
| `ai-agent` → `nodes-graph` | `domain/ports/` | NodeDefinitionRepository ABC |
| `ai-agent` → `doc-parser` | `application/use_cases/` | ParseDocumentUseCase (청크 조회) |
| `execution-engine` → `toolset` | `application/use_cases/` | ExecuteToolUseCase |
| `execution-engine` → `auth` | `domain/services/` | CredentialInjectionService |
| `storage` → 다른 모듈 `domain/ports/` | ABC만 import (구현 목적) | SessionRepository ABC |

---

## 15. 마이그레이션 가이드

현재 MONOREPO_STRUCTURE.md의 flat 구조에서 Clean Architecture로 전환하는 단계.

### 15.1 단계별 전환

| 단계 | 작업 | 영향 범위 | 우선순위 |
|------|------|----------|---------|
| **1** | `packages/common-schemas/` 내부 파일 구조화 (현재 13개 모듈 → 정리) | REQ-012 | P0 |
| **2** | `modules/storage/` 에 `orm/`, `repositories/`, `mappers/` 하위 구조 생성 | REQ-008 | P0 |
| **3** | 각 `modules/*/` 에 `domain/`, `application/`, `adapters/` 3계층 생성 | REQ-002~006 | P0 |
| **4** | `services/api-server/` 에 `dependencies/`, `middleware/` 구조화 | REQ-009 | P0 |
| **5** | `services/execution-engine/` 내부 Clean Architecture 적용 | REQ-007 | P0 |
| **6** | 기존 flat 파일을 각 계층으로 이동 + import 경로 갱신 | 전체 | P1 |
| **7** | CI에 import 방향 검증 추가 (import-linter 등) | CI/CD | P2 |

### 15.2 파일 이동 매핑 (REQ-002 예시)

| 현재 경로 | → 신규 경로 |
|-----------|-----------|
| `modules/auth/oauth.py` | `modules/auth/adapters/google_oauth.py` |
| `modules/auth/jwt.py` | `modules/auth/adapters/jwt_adapter.py` |
| `modules/auth/permissions.py` | `modules/auth/domain/services/permission_resolver.py` |
| `modules/auth/middleware.py` | `modules/auth/adapters/middleware.py` |
| (신규) | `modules/auth/domain/ports/session_repository.py` |
| (신규) | `modules/auth/domain/ports/cipher_port.py` |
| (신규) | `modules/auth/application/use_cases/authenticate.py` |

### 15.3 검증 도구

```toml
# pyproject.toml — import-linter 설정 예시
[tool.importlinter]
root_packages = ["common_schemas", "modules", "services"]

[[tool.importlinter.contracts]]
name = "Domain layer independence"
type = "forbidden"
source_modules = ["modules.*.domain"]
forbidden_modules = ["sqlalchemy", "fastapi", "celery", "langchain", "langgraph"]

[[tool.importlinter.contracts]]
name = "No reverse imports"
type = "layers"
layers = ["services", "modules", "packages"]
```

---

## 부록 A. 용어 정리

| 용어 | 정의 | 프로젝트 내 위치 |
|------|------|----------------|
| **Entity** | 도메인의 핵심 비즈니스 객체 (ID 보유) | `common-schemas/` + `modules/*/domain/entities/` |
| **Value Object (VO)** | 불변 값 객체 (ID 없음, 동등성으로 비교) | `common-schemas/` + `modules/*/domain/value_objects/` |
| **Domain Service** | 단일 엔티티에 속하지 않는 비즈니스 로직 | `modules/*/domain/services/` |
| **Port** | 도메인이 정의하는 인터페이스 (ABC) | `modules/*/domain/ports/` |
| **Adapter** | Port의 구현체 (외부 시스템 연동) | `modules/*/adapters/` + `modules/storage/` |
| **Use Case** | 하나의 사용자 시나리오를 오케스트레이션 | `modules/*/application/use_cases/` |
| **DI (Dependency Injection)** | 런타임에 Port에 Adapter를 주입 | `services/*/dependencies/` |
| **SSOT** | Single Source of Truth (공유 타입 단일 정의) | `packages/common-schemas/` |
| **Mapper** | ORM ↔ 도메인 엔티티 양방향 변환 | `modules/storage/mappers/` |

---

> **본 문서는 팀 리뷰 후 Accepted로 전환하며, 구현 시작 전 담당자별 확인을 거친다.**
