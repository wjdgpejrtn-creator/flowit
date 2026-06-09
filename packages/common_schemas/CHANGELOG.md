# Changelog

All notable changes to `common_schemas` will be documented in this file.

This project follows [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes to existing model fields (rename, type change, removal)
- **MINOR**: New models, new optional fields, new enum members
- **PATCH**: Documentation, codegen improvements, internal refactoring

## [0.22.0] - 2026-06-09

### Added — 비실재 노드 검증 코드 (ADR-0026 §6.6)

- `enums.py` `ErrorCode.E_UNKNOWN_NODE_TYPE` 추가 — 워크플로우 노드가 카탈로그에 실재하지 않는 node_type/node_id를 참조할 때 `GraphValidator`가 검증 시점에 거부하는 코드. LLM이 임시 생성한 비실재 노드가 QA를 통과한 뒤 실행 단계에서 executor 없어 실패하는 것을 차단(방어 심층 — compose+execute 공통 chokepoint). 신규 enum 멤버 → MINOR. TS `ErrorCode` regenerate 반영.

### Fixed — stale enum count 테스트 교정 (drive-by)

- `test_enums.py` `ErrorCode`(7→9) / `IntentType`(5→9) member_count assertion이 직전 멤버 추가(E_INVALID_TRIGGER, fast-path IntentType 4종) 후 갱신 누락돼 red였던 것을 실제 수에 맞게 교정. CI에 enum 테스트 게이트 부재로 미검출됐던 것 — 본 변경으로 green 복구.

## [0.21.0] - 2026-06-08

### Added — OAuth connection 상태 (ADR-0027)

- `connection.py` `ConnectionStatus`(service/connected/status/display: str|None) 추가 — settings 통합 탭 + `GET /api/v1/connections` 응답의 **단일 SSOT**. `ListConnectionsUseCase` 반환 ↔ api_server 응답 ↔ frontend 타입 공유로, use case VO(dataclass) ↔ api response(pydantic) 중복 제거(셀프리뷰 LOW). 신규 모델 → MINOR. TS regenerate(`ConnectionStatus` interface 자동 반영).

## [0.20.0] - 2026-06-05

### Added — 스킬 지침서 묶음 (노드측 / composer측 분리, #372 결함 A·B 해소)
- `skill_document.py` `SkillDocument`에 `composer_instructions: str = ""` 추가 — **composer측 지침서**(COMPOSER.md). ai_agent drafter가 워크플로우 생성 시 주입해 "이 스킬을 쓰려면 어떤 노드를 어떻게 엮어야 하는가"(예: LLM 노드 + Email 노드 필수)를 명시 → drafter가 LLM 노드를 포함해 바인딩 성립(#372 결함 A 해소). 기존 `instructions`(SKILL.md, **노드측** — execution_engine `_inject_skill`이 LLM 노드 system에 주입)와 소비처·시점이 완전히 분리됨.
- `instructions: str`를 `instructions: str = ""`로 완화 — 노드 지침/composer 지침 **둘 다 optional**(#372 detail 3: composer 지침만 있는 스킬, 노드 지침만 있는 스킬 모두 허용).
- 신규 optional 필드 + 기존 필드 완화(required→optional, 더 허용적) → MINOR. `__all__` 카운트(77) 불변(SkillDocument 기존 export). TS regenerate 완료 — `SkillDocument`에 `composer_instructions: string` 자동 반영(이 생성기는 default 있는 str도 `?` 없이 `string`으로 출력 — 기존 `instructions`와 동일 패턴).
- 저장 계약(storage): `GcsSkillDocumentStore`가 `skills/{skill_id}/SKILL.md` + `skills/{skill_id}/COMPOSER.md`(composer_instructions 비어있지 않을 때만)로 멀티파일 저장. `save()` 반환 URI는 호출부 계약 유지를 위해 항상 SKILL.md.

> ⚠️ TS `package.json` 버전이 0.15.0에 머물러 있어(이전 PR들에서 미동기화 누적) 이번에 0.20.0으로 동기화. private 패키지라 소비처는 generated 타입을 직접 import.

## [0.19.0] - 2026-06-04

### Added — credential 복수화 (멀티커넥션 노드 지원, REQ-012)
- `workflow.py` `NodeInstance`에 `credential_ids: dict[str, UUID] = {}` 추가 — provider(service)별 credential 바인딩. 멀티커넥션 노드(예: `required_connections=["slack","google"]`)가 connection을 모두 충족할 수 있게 한다. key는 `required_connections`의 provider 문자열.
  - 기존 `credential_id`(단수)는 legacy 단일 바인딩으로 유지 — provider 미지정이라 node 정의의 `required_connections`로 추론. default None이라 기존 workflows JSONB row 역호환(`NodeInstance.model_validate`).
  - 신규 메서드 `resolve_credentials(required_connections) -> dict[str, UUID]`: `credential_ids` 우선 + 단일 connection이면 legacy `credential_id`를 해당 provider에 매핑(하위호환). validator(provider 검증)·CredentialInjectionService·execution_engine이 공통 소비.
- `node.py` `NodeContext`에 `connection_tokens: dict[str, str] = {}` 추가 — provider별 해결된 connection 토큰. `CatalogNodeExecutor`가 노드의 모든 required connection을 inject해 채운다. `connection_token`(단수)은 단일 노드 하위호환 primary 토큰으로 유지. `wipe()`가 둘 다 제거.
- 신규 Optional 필드(기존 필드 변경 없음) → MINOR. TS regenerate 완료 — `NodeInstance.credential_ids?: Record<string, string>`, `NodeContext.connection_tokens?` 자동 반영.

## [0.18.0] - 2026-05-31

### Added — 스킬 선택 SSE 프레임 (REQ-013 two-shot HITL 생산자)
- `transport/sse.py`:
  - `SkillSelectionFrame` 신규 — 스킬 검색 후 사용자에게 적용할 스킬을 옵션으로 제시(two-shot 1차). `prompt` + `options: list[SkillOption]` + `field_name`("skill_selection") + `allow_skip`. 프론트가 옵션 렌더 → 사용자 선택 → `POST /sessions/{id}/slot`로 2차 트리거.
  - `SkillOption` 신규(중첩 모델) — `skill_id` + `name` + `description` + `document_preview?`(SkillDocument.instructions 미리보기) + `node_definition_id?`(노드형 호환, 지침서형은 None).
  - `AnySSEFrame` Union에 `Tag("skill_selection")` 등록. `SlotFillQuestionFrame`(question/field_name만)은 복수 옵션·skill_id 불가라 신규 프레임 채택.
- 신규 프레임/모델(기존 변경 없음) → MINOR. TS regenerate 완료.

## [0.17.0] - 2026-05-31

### Added — 스킬 런타임 주입 바인딩 (REQ-013 코어)
- `workflow.py` `NodeInstance`에 `skill_id: Optional[UUID] = None` 추가. 노드에 바인딩된 SkillDocument(도메인 지침서)를 가리키며, execution_engine이 LLM 노드(`category=="ai"`이면서 input_schema에 `system` 필드 보유) 실행 시 해당 스킬의 `instructions`를 `system` 프롬프트에 주입한다. `credential_id`(노드별 외부 참조)와 동일 패턴.
- 신규 Optional 필드(기존 필드 변경 없음) → MINOR. default None이라 기존 workflows JSONB row 역호환(`NodeInstance.model_validate`).
- 바인딩 소스(노드에 skill_id를 박는 것)는 Composer two-shot HITL 후속 PR. 본 변경은 필드 + 실행 시 소비(주입)만 추가.
- TS regenerate 완료 — `NodeInstance` 인터페이스에 `skill_id?: string | null` 자동 반영.

## [0.16.0] - 2026-05-31

### Added — 컨펌 게이트 신뢰 매니페스트 (confirm-gate-explanation)
- `workflow_explanation.py` 신규 — one-shot(HITL 없음) 철학에서 신뢰가 몰리는 최종 컨펌 게이트용 구조화 설명. AI 워크플로우 초안을 실행하기 전 "무엇을 하고/무엇을 건드리며/무엇을 가정했는지"를 사용자에게 노출한다.
  - `WorkflowExplanation`: `intent_restatement`(의도 재진술) · `summary`(평문 요약) · `steps` · `permissions` · `assumptions`.
  - `ExplanationStep`: `order` · `node_name` · `description` · `risk_level` — 노드 1개 = 단계 1개.
  - `PermissionItem`: `connection` · `node_name` · `risk_level` — `NodeConfig.required_connections` 원소를 권한 매니페스트로 노출.
- 전부 신규 모델(기존 필드 변경 없음) → MINOR. steps/permissions/assumptions는 `WorkflowSchema`+`NodeConfig`에서 결정론적으로 추출되는 사실 계약이며, summary만 LLM 다듬기 허용(설계 원칙: §docs/specs/plan/confirm-gate-explanation.md).
- `ResultFrame.payload["explanation"]`에 직렬화되어 orchestrator→api→프론트로 흐른다. 소비처: ai_agent composer `_explain_node`(영역 C) + frontend `ConfirmCard`(영역 D).
- TS regenerate 완료 — `WorkflowExplanation` / `ExplanationStep` / `PermissionItem` 인터페이스 자동 생성.

## [0.15.0] - 2026-05-30

### Added — 문서 파싱 커버리지 노출 (REQ-009 — analyze 결과 가시화)
- `document.py`:
  - `DocumentBlock` 도메인 엔티티에 `coverage: Optional[ParseCoverage] = None` 추가. QualityGate가 산출한 페이지/블록 종류별 커버리지를 문서에 실어 storage→api→프론트로 흐르게 한다. 기존엔 `QualityGateResult.coverage`가 계산만 되고 `save_quality_log`에서 드롭돼 어디에도 노출 안 됐다.
  - `DocumentBlocksResponse`에 동일 `coverage` 필드 추가 — `GET /api/v1/documents/{id}/blocks`가 분석 완료 시 커버리지 반환.
  - `DocumentBlock`이 뒤에 정의된 `ParseCoverage`를 전방 참조하므로 파일 끝 `DocumentBlock.model_rebuild()` 추가.
- 둘 다 `Optional` 신규 필드 → MINOR. `ParseCoverage`는 기존 정의/TS export 재사용(신규 타입 없음).
- TS regenerate 완료 — `DocumentBlock` / `DocumentBlocksResponse` 인터페이스에 `coverage` 자동 반영.

## [0.14.0] - 2026-05-29

### Added — 문서 분석 상태 추적 (REQ-009/REQ-007 — 분석 결과 read path 완성)
- `enums.py`: `AnalysisStatus(pending|running|completed|failed)` 신설. Celery worker가 갱신, api_server가 응답에 노출. 기존엔 `DocumentResponse.is_analyzed` boolean만 있어 "진행중"과 "실패"를 구분 못 했고, 프론트엔드가 폴링으로 완료를 감지할 수 없었다.
- `document.py`:
  - `DocumentBlock` 도메인 엔티티에 `analysis_status: AnalysisStatus` / `analysis_error` / `analyzed_at` 필드 추가.
  - `DocumentResponse`에 동일 필드 추가 — 메타 폴링 응답에서 상태 노출. `is_analyzed`는 호환성 위해 유지(=`status == AnalysisStatus.COMPLETED`).
  - `DocumentBlocksResponse` 신규 — `GET /api/v1/documents/{id}/blocks` 본문 전용 DTO. 메타와 분리해서 분석 완료 후 1회만 fetch.
  - 3 스키마 모두 `AnalysisStatus` enum 직접 참조(`Literal` 미사용) — SSOT 활용 일관.
- TS regenerate 완료.

## [0.13.0] - 2026-05-28

### Added — `ErrorCode.E_MISSING_REQUIRED_PARAMETER` (PR #208 후속)
- `enums.py`: 워크플로우 노드의 `input_schema.required` 중 `NodeInstance.parameters`에 없는 필드를 `GraphValidator`가 보고할 때 사용. 기존엔 connection 누락(`E_MISSING_CONNECTION`)만 검사해 사용자가 `prompt` 같은 필수 파라미터를 안 넣어도 validate가 passed로 떨어지고 execute 시점에 worker가 `__init__() missing 1 required positional argument` 런타임 에러를 던지는 갭이 있었다.
- 매핑: `GraphValidator._check_required_parameters`가 본 코드로 노드별 누락 필드를 `ValidationErrorItem(message="Required parameter(s) missing: ...")` 으로 반환.
- TS regenerate 완료.

## [0.12.0] - 2026-05-23

### Added — `UserRole` named Literal (PR #157 review ① SSOT 통합)
- `security.py`: `UserRole = Literal["User", "team_manager", "company_manager", "Admin"]` 신설. `PermissionSource.role: UserRole`로 참조. `auth.domain.entities.user.UserRole`은 본 심볼의 re-export로 전환되어 두 곳 독립 정의로 인한 drift(향후 role 추가 시 한쪽만 바뀌면 런타임 ValidationError) 위험 제거.

### Changed — `PermissionSource.role`에 매니저 역할 2종 추가 (스킬 마켓플레이스 RBAC, PR #150 위임2)
- `security.py`: `PermissionSource.role` Literal `["User", "Admin"]` → `["User", "team_manager", "company_manager", "Admin"]` (현재는 `UserRole` named alias로 표현). 스킬 마켓플레이스 team/company scope 승인 인가용 — `SkillApprovalPolicy`가 `actor.role`로 승인 권한을 판정한다.
- 짝 변경: `users.role` CHECK (`database/schemas/021_user_roles_expand.sql`). `auth` 측은 common_schemas re-export로 자동 정합.

### Changed
- TypeScript codegen: `PermissionSource.role` union이 4종으로 `generated/index.ts`에 자동 반영 (pydantic2ts는 named alias도 인라인 union으로 직렬화 — 소비자 무영향).
- `test_security.py` — `team_manager`/`company_manager` 허용 검증 + `UserRole.__args__` 4-set 검증 추가.
- `auth/tests/unit/domain/test_user.py` — `auth.UserRole is common_schemas.UserRole` SSOT identity 검증 추가.

### Symbols
- 66 → 67 (`UserRole` 신규 top-level export).

### Migration notes
- 순수 additive — `PermissionSource.role` 기존 `"User"`/`"Admin"` 값 유효. `from common_schemas import UserRole` 신규 가능, `from auth.domain.entities.user import UserRole`도 그대로 동작(re-export shim).

## [0.11.0] - 2026-05-22

### Added — 파싱 품질/청킹 타입 6종 SSOT 이관 (REQ-006 doc_parser → common_schemas)
- `document.py`: `WarningInfo`, `QualityMetrics`, `ParseCoverage`, `QualityGateResult`, `Chunk`, `ChunkingStrategy` — `doc_parser.domain.entities`에서 이관. doc_parser가 자체 정의하던 타입을 common_schemas SSOT로 단일화 (storage `DocumentRepositoryPort`/`PgDocumentRepository`, ai_agent가 경계를 넘어 공유).
- `ParseCoverage`는 CLAUDE.md SSOT 표 누락분 — `QualityGateResult.coverage`의 타입이라 함께 이관(없으면 `QualityGateResult` 정의 불가).

### Changed
- TypeScript codegen: 6종 인터페이스 `generated/index.ts`에 자동 반영.
- `test_document.py` — 6종 단위 테스트 12건 추가 (frozen/default/Literal 검증).
- doc_parser `chunk.py`/`quality.py`/`warning.py`는 common_schemas 재노출 shim으로 전환 — `doc_parser.domain.entities.*` 기존 import 무변경 동작. `QualityConfig`/`ElapsedDetail`은 doc_parser 내부 타입이라 잔류.

### Symbols
- 60 → 66 (`WarningInfo`, `QualityMetrics`, `ParseCoverage`, `QualityGateResult`, `Chunk`, `ChunkingStrategy` 신규 top-level export)

### Migration notes
- 순수 additive — 기존 타입/필드 무변경. doc_parser 측은 shim 유지로 기존 import 경로(`from doc_parser.domain.entities...`) 그대로 동작. 신규 코드는 `from common_schemas import ...` 권장.

## [0.10.0] - 2026-05-22

### Added — `ChatMessageFrame` SSE 프레임 (REQ-004 실시간 모니터링 요청)
- `transport/sse.py`: `ChatMessageFrame(SSEFrame)` — `frame_type: "chat_message"`, `role: Literal["user", "assistant"]`, `content: str`. 유저 입력·AI assistant 응답 본문을 운반.
- `AnySSEFrame` discriminated union에 `chat_message` 태그 추가.
- 배경: `SessionFrameStore`가 파이프라인 상태 프레임(`AgentNodeFrame` / `PipelineStatusFrame` / `ResultFrame` 등)만 기록해 모니터링에서 대화 내용을 재생할 수 없었음. 본 프레임으로 유저 메시지·assistant 응답을 함께 기록할 수 있다.

### Changed
- TypeScript codegen: `ChatMessageFrame` 인터페이스 + `AnySSEFrame` union에 자동 반영 (`generated/index.ts`).
- `test_transport.py` — `ChatMessageFrame` 단위 테스트 2건 + `AnySSEFrame` discriminator 테스트 1건 추가.

### Symbols
- 59 → 60 (`ChatMessageFrame` 신규 top-level export)

### Migration notes
- 없음 — 순수 additive(신규 프레임 추가만, 기존 프레임/필드 무변경). `AnySSEFrame` 소비자는 새 `chat_message` 케이스 처리를 추가하는 것을 권장하나 미처리해도 기존 동작은 깨지지 않는다.

## [0.9.0] - 2026-05-21

### Added — `ContentBlock` / `DocumentBlock` 파싱 커버리지 필드 4종 (PR #60 리뷰 후속, REQ-006 doc_parser 요청)
- `ContentBlock.metadata: Optional[dict[str, Any]] = None` — 블록 부가 메타데이터. XLSX 병합셀 3층 구조(`data_rows` / `normalized_headers` 등) 데이터 운반용. `QualityGate._calc_valid_table_ratio()`의 `isinstance(table[0], dict)` 분기를 정식 필드로 대체.
- `ContentBlock.is_corrupted: bool = False` — 깨진 블록 마킹. `QualityGate`가 깨진 블록 비율을 집계할 때 사용.
- `DocumentBlock.vision_block_count: int = 0` — 비전 추출로 생성된 블록 수.
- `DocumentBlock.failed_block_count: int = 0` — 비전 추출 실패 횟수(`VisionPort.extract()` → `None`).

### Changed
- TypeScript codegen: `ContentBlock` / `DocumentBlock` 인터페이스에 4개 필드 자동 반영 (`generated/index.ts`).
- `test_document.py` — `ContentBlock` 신규 필드 2건 + `DocumentBlock` 커버리지 카운트 2건 테스트 추가 (109 → 113).

### Symbols
- 59 → 59 (기존 모델 필드 추가만 — 신규 top-level export 없음)

### Migration notes
- 추가만 있는 변경 — 모든 필드가 default 보유, 기존 코드 무영향.
- 배경: `InterleavingParser`는 비전 성공(`extract()` → `ContentBlock`) / 실패(`extract()` → `None`)를 이미 분기 감지하지만, 실패 시 `else` 분기는 블록을 0개 생성하므로 per-block 마커로는 집계 불가. `failed_block_count`는 `DocumentBlock` 레벨 운반 필드로만 `QualityGate`까지 전달 가능.
- **후속 (김진형, REQ-006 별도 PR)**:
  - `InterleavingParser._rebuild_doc()` — `vision_block_count` / `failed_block_count` 채워서 `DocumentBlock` 생성.
  - `QualityGate._calc_coverage()` — `vision_blocks=0` / `failed_blocks=0` 하드코딩(TODO)을 `document.vision_block_count` / `document.failed_block_count`로 교체.
  - `QualityGate._calc_valid_table_ratio()` — XLSX 분기를 `ContentBlock.metadata` 기반으로 정리.
  - `ContentBlock.metadata` 키 규약(XLSX 병합셀 `data_rows` / `normalized_headers` 등) — 생산자(xlsx_parser) ↔ 소비자(QualityGate) drift 방지 위해 `TypedDict` 또는 별도 모델로 명문화 검토 (PR #120 리뷰 🟢 LOW). `metadata` 자체는 범용 확장 슬롯이므로 `dict[str, Any]` 유지, 키 규약만 doc_parser 측에서 명문화.
  - `tests/conftest.py`의 `common_schemas` stub 제거 (common_schemas 0.9.0 머지 후).

## [0.8.0] - 2026-05-20

### Added — `SkillDocument` 스킬 지침서 (ADR-0017, PR #106 리뷰)
- `skill_document.py` 모듈 신설 — `SkillDocument` Pydantic 모델 1종.
- `SkillDocument`: `skill_id: UUID`, `name: str`, `description: str`, `instructions: str`, `scripts: list[dict] = []`, `templates: list[dict] = []`.
  - 한 스킬의 ADR-0017 이중 저장 중 "지침서"(SKILL.md) 측. 메타는 `NodeDefinition` + `SkillRepository`.
  - LLM(Main Agent)이 사용자에게 옵션 제시 시 자연어로 읽는 markdown 문서. 저장: GCS `gs://{bucket}/skills/{skill_id}/SKILL.md` via `SkillDocumentStore`.
  - `frozen=True` — 불변 데이터 캐리어 (common_schemas 모델 표준 컨벤션).
- 신규 테스트 `test_skill_document.py` — `SkillDocument` 8건.

### Changed — `SkillDocument` SSOT 위치 정정
- PR #106 리뷰에서 지적: `SkillDocument`는 **생산자 ai_agent(Skills Builder) + 저장자 skills_marketplace(SkillDocumentStore)** 양쪽이 쓰는 공유 타입.
  ADR-0017의 skills_marketplace 도메인 소유로는 ai_agent가 import 규칙상 직접 참조 불가 → PR #106은 dict로 우회(type 안전성 상실).
- `common_schemas`로 승격하면 모든 모듈이 import 가능 → import 규칙 위반 없이 type-safe 공유. SSOT 위치를 skills_marketplace → common_schemas로 정정.

### Symbols
- 58 → 59 (+1: `SkillDocument`)

### Migration notes
- common_schemas 측은 추가만 있는 변경 — 기존 코드 무영향.
- 신규 사용 패턴:
  ```python
  from common_schemas import SkillDocument
  ```
- **후속 (박아름, 별도 PR)**: `modules/skills_marketplace/domain/entities/skill_document.py`를 common_schemas 재노출 shim으로 전환 + `SkillDocumentStore` Port가 `common_schemas.SkillDocument` 사용. ai_agent 3 use case의 `skill_documents` dict → `SkillDocument` 객체로 정정 (type-safe). ADR-0017 소유권 문구 정정.
- skills_marketplace 측 `SkillDocument`(PR #98)는 필드 동일 — shim 전환 시 기존 테스트 무변경 통과.

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
