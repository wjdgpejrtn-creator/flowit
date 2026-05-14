# Changelog

All notable changes to `common_schemas` will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes to existing model fields (rename, type change, removal)
- **MINOR**: New models, new optional fields, new enum members
- **PATCH**: Documentation, codegen improvements, internal refactoring

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
