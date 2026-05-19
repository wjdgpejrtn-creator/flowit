# Changelog

All notable changes to `common_schemas` will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes to existing model fields (rename, type change, removal)
- **MINOR**: New models, new optional fields, new enum members
- **PATCH**: Documentation, codegen improvements, internal refactoring

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
