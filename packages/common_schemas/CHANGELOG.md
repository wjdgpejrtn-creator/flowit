# Changelog

All notable changes to `common_schemas` will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes to existing model fields (rename, type change, removal)
- **MINOR**: New models, new optional fields, new enum members
- **PATCH**: Documentation, codegen improvements, internal refactoring

## [0.7.0] - 2026-05-20

### Added — `NodeContext` 노드 실행 컨텍스트 (ADR-0018 Phase 1)
- `node.py` 모듈 신설 (기존엔 placeholder) — `NodeContext` Pydantic 모델 1종.
- `NodeContext`: `execution_id: UUID`, `user_id: UUID`, `connection_token: Optional[str] = None`.
  - ADR-0018에 따라 워크플로우 노드 실행 경로가 `BaseNode.process(input, context)`로 확장될 때 `CatalogNodeExecutor`가 노드에 전달하는 1회 실행분 컨텍스트.
  - `connection_token`은 해결된 connection 토큰 — connection이 필요한 external 노드만 사용, domain 28종은 무시.
  - `frozen=False` + `wipe()` 메서드 — `process()` 종료 후 평문 토큰 제거 (`PlaintextCredential`과 동일 패턴, ADR-0018 Decision 5).
- 신규 테스트 `test_node.py` — `NodeContext` 6건.

### Changed
- `typescript/package.json` version `0.3.0` → `0.7.0` — Python 패키지 버전과 drift 누적분 재동기화 (0.4.0~0.6.2 동안 미반영). 이후 두 곳 동시 bump 유지.

### Symbols
- 57 → 58 (+1: `NodeContext`)

### Migration notes
- 추가만 있는 변경 — 기존 코드 무영향.
- 본 PR은 타입 정의만 추가한다. `BaseNode.process()` 시그니처 확장(nodes_graph, REQ-003 박아름) + `CatalogNodeExecutor` 신규(execution_engine, REQ-007)는 ADR-0018 Phase 1 후속 작업.
- 신규 사용 패턴:
  ```python
  from common_schemas import NodeContext
  ```

## [0.6.2] - 2026-05-19

### Added — broker task name 상수 모듈 (PR #75 리뷰 #4 반영)
- `common_schemas.broker_tasks` 모듈 신설 — Celery task name 단일 정의 (`TASK_EXECUTE_WORKFLOW` / `TASK_CANCEL_EXECUTION` / `TASK_RESUME_EXECUTION` / `TASK_EXECUTE_NODE` / `TASK_HANDLE_HANDOFF` / `TASK_LEVEL_CALLBACK` + `QUEUE_DEFAULT`).
- 이전엔 api_server router (`workflows.py` / `exec_control.py`) + execution_engine `_celery_app.py task_routes` + `celery_tasks.py @shared_task name=...` + `celery_adapter.py EXECUTE_WORKFLOW_TASK_NAME` 4곳에 같은 문자열이 중복. SSOT 도입으로 drift 방지.

### Symbols
- 56 → 57 (+1: `broker_tasks` 모듈, 단일 namespace로 export)

### Migration notes
- 기존 매직 문자열 호출자는 점진 교체:
  ```python
  from common_schemas.broker_tasks import TASK_EXECUTE_WORKFLOW
  celery.send_task(TASK_EXECUTE_WORKFLOW, args=[...])
  ```
- 본 PR(#75)에서 api_server 측은 모두 교체. execution_engine 측 decorator는 후속 PR (decorator import-time evaluation 안전 검토 후).

## [0.6.1] - 2026-05-19

### Added — ExecutionStatus enum 멤버 2종 (PR-A, REQ-007 cancel/resume 실 구현 동반)
- `ExecutionStatus.PENDING` (값 `"pending"`) — 신규 execution insert 직후 task pickup 전 상태. DB CheckConstraint `ck_executions_status`는 이미 `pending` 허용 — enum과 DB 정합 회복.
- `ExecutionStatus.CANCELLED` (값 `"cancelled"`) — `/executions/{id}/cancel` 후 Celery `revoke` + 마킹. DB CheckConstraint `cancelled` 허용과 정합.

### Changed
- `ExecutionStatus` 멤버 수 4 → 6. `test_enums.py` 갱신.
- DB CheckConstraint와 enum 사이 사각지대 해소 (이전: DB는 6종 허용 / enum은 4종 노출).
- `enums.py`에 동일 이름으로 두 번 정의돼 있던 `IntentType` 중복 정의 제거 (Python에서는 후위 정의가 덮어쓰는 형태였어 동작상 차이는 없었음). 결과적으로 첫 위치 1건이 제거되고 끝부분 1건만 잔존 — 멤버/값 동일하여 외부 영향 없음.

### Symbols
- 56 → 56 (enum 멤버 추가만, 신규 symbol 없음)

### Migration notes
- 기존 코드 무영향 (멤버 추가만).
- `ExecutionOrchestrator.VALID_TRANSITIONS` 확장 동반 (services/execution_engine 측 동일 PR) — `PENDING → RUNNING`, `{RUNNING, PAUSED} → CANCELLED` 전환 허용.
- 사용 예시:
  ```python
  from common_schemas import ExecutionStatus
  if exec.status in {ExecutionStatus.RUNNING, ExecutionStatus.PAUSED}:
      ...  # cancellable
  ```

## [0.6.0] - 2026-05-19

### Added — SSE 모니터링 프레임 4종 (PR #74, 신정혜 + 황대원 common_schemas 보강)
- `transport.sse.PipelineStatusFrame` — 생성 파이프라인 각 서비스 진행 상태 (`service_name`, `status: Literal["started","completed","failed"]`, `elapsed_ms`). 오른쪽 사이드바 실시간 표시용.
- `transport.sse.IntentResultFrame` — 의도 분석 결과 (`intent`, `entities`). 오른쪽 사이드바 표시용.
- `transport.sse.QAMetricFrame` — QA 평가 결과 (`score`, `attempt`, `pass_flag`, `feedback`). 오른쪽 사이드바 표시용.
- `transport.sse.WorkflowDraftFrame` — 워크플로우 초안 (`nodes`, `connections`). 가운데 캔버스 실시간 시각화용.
- `AnySSEFrame` discriminated union에 4종 Tag 추가 (`pipeline_status`/`intent_result`/`qa_metric`/`workflow_draft`).

### Changed
- `common_schemas.__init__` + `transport/__init__.py`에 4종 re-export 추가.
- TypeScript codegen: 4개 인터페이스 자동 생성 (`generated/index.ts`).

### Symbols
- 52 → 56 (+4: `PipelineStatusFrame`, `IntentResultFrame`, `QAMetricFrame`, `WorkflowDraftFrame`)

### Migration notes
- 추가만 있는 변경 — 기존 코드 무영향.
- 신규 사용 패턴 (composer_graph 각 노드에서 emit, supervisor가 Queue로 relay):
  ```python
  from common_schemas import PipelineStatusFrame, IntentResultFrame, QAMetricFrame, WorkflowDraftFrame
  ```

## [0.5.0] - 2026-05-19

### Added — ADR-0015 §D4 LLM tool-use transport SSOT
- `transport/llm.py` 신설 — `Message`, `ToolCall`, `LLMResponse` 3개 Pydantic 모델. ADR-0015 호출 경로 B (LLM tool-use) 인프라의 기반 타입. `LLMPort.generate(messages: list[Message], tools=...) -> LLMResponse` 시그니처가 본 타입을 사용 (F2 신정혜 PR-A 의존).
- `Message`: `role: Literal["system","user","assistant","tool"], content: str, tool_call_id: str|None, name: str|None`
- `ToolCall`: `id: str, name: str, arguments: dict[str, Any]` — LLM이 요청한 도구 호출 직렬화
- `LLMResponse`: `content: str|None, tool_calls: list[ToolCall], finish_reason: Literal["stop","tool_calls","length"]`
- 신규 테스트 `test_transport_llm.py` — Message 3건 + ToolCall 2건 + LLMResponse 3건 (총 8건)

### Changed — transport 모듈 구조
- `transport.py` (71줄 단일 파일) → `transport/` 디렉토리로 마이그레이션
  - `transport/sse.py` — 기존 SSE 프레임 7개 + `AnySSEFrame` discriminated union (내용 변경 없음)
  - `transport/llm.py` — 신규 LLM tool-use 타입 (위)
  - `transport/__init__.py` — 둘 다 re-export
- **외부 import 호환성 유지**: `from common_schemas.transport import SSEFrame` / `from common_schemas import SSEFrame` 모두 그대로 동작. 변경 사항 0.

### Symbols
- 49 → 52 (+3: `LLMResponse`, `Message`, `ToolCall`)

### Migration notes
- 기존 `from common_schemas.transport import SSEFrame` (또는 다른 SSE 프레임) 무영향.
- 신규 코드 권장 패턴: `from common_schemas import LLMResponse, Message, ToolCall` (또는 `from common_schemas.transport import ...`).
- `transport.py` 파일은 삭제되었으나 `transport/__init__.py`가 동일 symbol을 re-export하므로 import 경로 변경 불필요.

## [0.4.0] - 2026-05-18

### Added
- `enums.IntentType(str, Enum)` 신설 — 5값(`CLARIFY`, `DRAFT`, `REFINE`, `PROPOSE`, `BUILD_SKILL`) SSOT. PR #70 (신정혜) 후속 권고: `route_request_use_case.py` + `intent_analyzer_service.py`의 문자열 리터럴 분산 하드코딩 일원화.

### Changed
- `agent.IntentResult.intent` 타입 `Literal["clarify", "draft", "refine", "propose", "build_skill"]` → `IntentType`. **호환성 유지**: `str` 상속 Enum이므로 기존 문자열 입력(`IntentResult(intent="draft", ...)`)은 그대로 동작하고 validation 후에는 `IntentType.DRAFT` 인스턴스가 됨.
- TypeScript codegen: `IntentResult.intent: IntentType` enum 참조로 변경 (`generated/index.ts`).

### Migration notes
- **기존 `==` 비교는 모두 무영향**: `ir.intent == "draft"` ↔ `IntentType.DRAFT == "draft"` 모두 `True` (StrEnum 값 비교).
- **신규 권장 패턴**: `if intent_result.intent is IntentType.BUILD_SKILL:` — IDE 자동완성/타입체크 강화.
- **기존 `isinstance(..., str)` 체크 무영향**: `IntentType.DRAFT`는 `str` 인스턴스이기도 함.

### Symbols
- 48 → 49 (+1: `IntentType`)

## [0.3.0] - 2026-05-14

### Added
- `workflow.WorkflowSchema.owner_user_id: Optional[UUID] = None` — 워크플로우 소유자(creator). DB schema는 `001_core.sql` `workflows.user_id NOT NULL`이라 Repository.save 시점에 필수, 도메인 모델은 점진 마이그레이션/역직렬화 호환을 위해 Optional. ADR-0012 v3 PR-2a-3.

### Migration notes
- 기존 `WorkflowSchema(...)` 호출은 무영향 (default `None`).
- DB 저장 경로: `WorkflowMapper.to_orm` 시 `owner_user_id is None`이면 `ValueError` raise (NOT NULL violation 방어 — 명시적 에러로 전환). DB INSERT 코드는 use case에서 owner_user_id를 명시적으로 채워서 mapper 호출.
- 기존 staging row 역직렬화는 안전 (`owner_user_id` 누락 시 default `None`).
- `scope`(private/team/public)와 직교 — `owner_user_id`는 작성자, `scope`는 공유 범위.

### Symbols
- 48 → 48 (필드 추가만, top-level export 변동 없음)

## [0.2.0] - 2026-05-12

### Added — Sprint 3 멀티 에이전트 구조 대응
- `agent_protocol` 모듈 신규: `AgentProtocolRequest`, `AgentProtocolResponse` (orchestrator ↔ sub-agent HTTP 통신 계약, Sprint 3 §2.4)
- `agent.MemoryEntry` 신규 — ai_agent 모듈에서 SSOT 이관 (`modules/ai_agent/domain/entities/memory_entry.py`는 호환용 재노출 shim)
- `agent.MemoryType` 별칭 — `Literal["preference","correction","workflow_pattern","summary"]`
- `agent.AgentState.personal_memory: list[MemoryEntry]` 필드 (기본 빈 리스트)
- `enums.AgentMode.SKILL_BUILDER` 멤버 추가
- `agent.IntentResult.intent` Literal에 `"build_skill"` 추가
- 신규 테스트: `test_agent_protocol.py`(5건), `MemoryEntry` 6건, `personal_memory` 2건

### Symbols
- 42 → 48 (+6: `MemoryEntry`, `MemoryType`, `AgentProtocolRequest`, `AgentProtocolResponse`, 그리고 enums/Literal 확장)

### Migration notes
- 기존 `from ai_agent.domain.entities import MemoryEntry`는 그대로 동작 — shim이 common_schemas에서 재노출
- 신규 코드는 `from common_schemas import MemoryEntry` 권장
- `AgentMode` 멤버 수 5→6: 기존 `len(AgentMode) == 5` 가정한 코드 갱신 필요

## [0.1.0] - 2026-05-05

### Added
- Initial release: 9 modules, 42 Python symbols (Pydantic v2)
- TypeScript codegen via `scripts/generate_ts.py` (auto-discovery + topo-sort)
- 32 interfaces + 4 enums + `AnySSEFrame` discriminated union
- CI codegen drift check + `tsc --noEmit` validation
- pytest 65 unit tests (all pass)
- PEP 561 `py.typed` marker

### Modules
- `enums`: AgentMode, ExecutionStatus, RiskLevel, ErrorCode
- `exceptions`: DomainError hierarchy
- `workflow`: Position, Edge, NodeInstance, NodeConfig, WorkflowSchema
- `document`: BBox, FileMeta, ContentBlock, DocumentBlock, AnalysisResult
- `agent`: AgentState, DraftSpec, IntentResult, SlotFillingState
- `transport`: SSE frame types + AnySSEFrame union
- `validation`: ValidationErrorItem, ValidationErrorResponse
- `security`: PermissionSource, PlaintextCredential
- `handoff`: HandoffPayload, EvaluationResult
