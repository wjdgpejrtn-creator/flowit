# REQ-005 Toolset 구현 개요

> **담당자**: 이가원
> **브랜치**: `feature/req-005-toolset`
> **기준 문서**: `docs/specs/REQ-005-toolset.md`, `modules/toolset/README.md`, `CLAUDE.md`
> **최종 업데이트**: 2026-05-05 (PR #11 merge 반영)

---

## 프로젝트에서 Toolset의 역할

Toolset은 워크플로우 실행 시 **외부 도구(Google Drive, Gmail, Slack 등)를 실행하는 어댑터 계층**이다.

```
execution-engine (REQ-007)
  → ExecuteToolUseCase (REQ-005)
    → RiskAssessmentService (권한 검사)
    → RuntimeValidator (입력 검증)
    → CredentialInjectionService (REQ-002, 자격증명 획득)
    → BaseTool.run(params, credential)
      → 외부 API (Google, Slack, Modal GPU ...)
    → RuntimeValidator (출력 검증)
    → ToolExecutionRepository.save() (실행 이력 저장)
```

- **실행 주체**: `services/execution-engine`이 DI로 `ExecuteToolUseCase`를 주입받아 호출
- **보안 흐름**: `PermissionSource.risk_ceiling` 검사 → Credential 획득 → 실행 → Credential 즉시 `wipe()`
- **노드 등록**: `nodes-graph`의 `ToolToNodeWrapper`가 `BaseTool` 메타데이터를 `NodeDefinition`으로 변환
- **이력 저장**: `ToolExecutionRepository` Port를 통해 `modules/storage`에 위임

---

## Phase 0 상태: ✅ DONE (PR #11 merged → development)

**REQ-012(황대원)이 `feature/req-012-common-schemas` → `development` PR #11로 merge 완료.**

이가원은 `packages/common-schemas/`를 직접 수정하지 않는다.
import만 하면 된다.

### 실제 구현된 타입 (반드시 이 값 사용)

```python
# RiskLevel — 값이 대소문자 구분됨 ("Low", "Medium", "High", "Restricted")
from common_schemas.enums import RiskLevel
# RiskLevel.LOW.value == "Low"
# RiskLevel.MEDIUM.value == "Medium"
# RiskLevel.HIGH.value == "High"
# RiskLevel.RESTRICTED.value == "Restricted"

# PermissionSource — risk_ceiling은 Literal["High", "Restricted"]
from common_schemas.security import PermissionSource
# ps.risk_ceiling == "High" 또는 "Restricted" (RiskLevel 타입이 아님!)

# PlaintextCredential — 필드명은 value (token 아님)
from common_schemas.security import PlaintextCredential
# cred.value == "평문 토큰값"
# cred.credential_kind == "fernet" or "aes_gcm"
# cred.wipe() → self.value = "" 로 단순 초기화

# 예외 클래스
from common_schemas.exceptions import (
    DomainError,         # base: __init__(message, *, code: str|None)
    ValidationError,     # 422
    AuthorizationError,  # 403
    ExecutionError,      # 500
    NotFoundError,       # 404
)
# ⚠️ CredentialError, ToolExecutionError, ConflictError 없음 → toolset 로컬 정의
```

### toolset 로컬 예외 (domain/exceptions.py에 추가 정의)

common_schemas에 없어서 toolset이 자체 정의해야 하는 예외들:

```python
# modules/toolset/domain/exceptions.py
from common_schemas.exceptions import DomainError

class ToolExecutionError(DomainError):
    """외부 API 호출 실패. HTTP 502."""

class CredentialError(DomainError):
    """자격증명 획득/복호화 실패. HTTP 401."""

class ConflictError(DomainError):
    """도구 중복 등록 등 충돌. HTTP 409."""
```

---

## 전체 구현 파일 목록

### modules/toolset/ (Phase 1~5)

```
modules/toolset/
├── domain/
│   ├── exceptions.py                        Phase 1  ← 로컬 예외 정의
│   ├── base_tool.py                         Phase 1  ← (또는 entities/base_tool.py)
│   ├── entities/
│   │   ├── __init__.py                      Phase 1
│   │   ├── base_tool.py                     Phase 1  ← BaseTool ABC
│   │   ├── tool_execution_record.py         Phase 1  ← 실행 이력 엔티티
│   │   └── tool_metadata.py                 Phase 1  ← 도구 카탈로그 메타데이터
│   ├── value_objects/
│   │   ├── __init__.py                      Phase 1
│   │   ├── tool_input.py                    Phase 1  ← 검증된 입력 VO
│   │   ├── tool_output.py                   Phase 1  ← 검증된 출력 VO
│   │   └── execution_timeout.py             Phase 1  ← 타임아웃 설정 VO
│   ├── services/
│   │   ├── __init__.py                      Phase 1
│   │   ├── runtime_validator.py             Phase 1  ← I/O 스키마 검증
│   │   ├── tool_execution_service.py        Phase 1  ← 실행 오케스트레이션
│   │   └── risk_assessment_service.py       Phase 1  ← 권한/위험도 검사
│   └── ports/
│       ├── __init__.py                      Phase 1
│       ├── tool_registry.py                 Phase 1  ← ToolRegistry ABC
│       ├── secure_connector_port.py         Phase 1  ← SecureConnectorPort ABC
│       └── tool_execution_repository.py     Phase 1  ← 실행이력 저장 Port
├── application/
│   ├── __init__.py                          Phase 2
│   └── use_cases/
│       ├── __init__.py                      Phase 2
│       ├── execute_tool_use_case.py         Phase 2  ← 메인 실행 유스케이스
│       ├── list_tools_use_case.py           Phase 2  ← 도구 목록 조회
│       └── validate_tool_config_use_case.py Phase 2  ← 설정 사전 검증
├── adapters/
│   ├── __init__.py                          Phase 3
│   ├── tool_registry_adapter.py             Phase 3  ← InMemory 구현체
│   ├── secure_connector.py                  Phase 3  ← auth 연동 구현체
│   ├── state_manager.py                     Phase 3  ← Redis+PG fallback
│   └── tools/
│       ├── __init__.py                      Phase 4
│       ├── webhook_tool.py                  Phase 4
│       ├── http_request_tool.py             Phase 4
│       ├── llm_tool.py                      Phase 4
│       ├── google_drive_tool.py             Phase 4
│       ├── gmail_tool.py                    Phase 4
│       ├── google_calendar_tool.py          Phase 4
│       ├── google_sheets_tool.py            Phase 4
│       └── slack_tool.py                    Phase 4
└── tests/
    ├── conftest.py                          Phase 5
    ├── unit/
    │   ├── domain/
    │   │   ├── test_base_tool.py            Phase 5
    │   │   ├── test_runtime_validator.py    Phase 5
    │   │   ├── test_tool_execution_service.py Phase 5
    │   │   └── test_risk_assessment_service.py Phase 5
    │   ├── application/
    │   │   ├── test_execute_tool_use_case.py Phase 5
    │   │   ├── test_list_tools_use_case.py   Phase 5
    │   │   └── test_validate_tool_config_use_case.py Phase 5
    │   └── tools/
    │       ├── test_webhook_tool.py          Phase 5
    │       ├── test_http_request_tool.py     Phase 5
    │       └── test_google_drive_tool.py     Phase 5
    └── integration/
        └── test_secure_connector.py          Phase 5
```

---

## 구현 순서

```
Phase 0 ✅ (완료) → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
```

### Phase 4 내부 권장 순서

```
webhook_tool       ← 가장 단순, httpx 패턴 파악
http_request_tool  ← webhook 변형
llm_tool           ← Modal 연동 패턴 확립
google_drive_tool  ← Google API 패턴 확립
gmail_tool         ← Google 패턴 재활용
google_calendar_tool
google_sheets_tool
slack_tool         ← 별도 SDK
```

---

## 레이어별 import 규칙

| 레이어 | 허용 import | 금지 |
|--------|------------|------|
| `domain/` | `common_schemas`, `abc`, `jsonschema`, stdlib | 프레임워크, adapters |
| `application/` | `domain/*`, `common_schemas` | 구현체 직접 import |
| `adapters/` | domain/ports, 외부 SDK, `auth.domain.services` | `services/*` 직접 참조 |

### cross-module import (CLAUDE.md 허용 목록)

```python
# adapters/secure_connector.py 에서 auth 직접 import 가능
from auth.domain.services import CredentialInjectionService
# → inject(credential_id: UUID, node_id: UUID) → PlaintextCredential
```

---

## 타 REQ 협업 포인트

| 대상 | 내용 | 시점 | 상태 |
|------|------|------|------|
| REQ-012 황대원 | common-schemas 타입 확정 | ✅ 완료 (PR #11) | Done |
| REQ-002 박아름 | `CredentialInjectionService.inject()` 시그니처 확인 (node_id 필요성) | Phase 3 전 | 대기 |
| REQ-007 황대원 | `ExecuteToolUseCase` 호출 패턴 전달 (tool_name, input_data, context) | Phase 2 완료 후 | 대기 |
| REQ-003 박아름 | `BaseTool` 메타데이터 구조 → `ToolToNodeWrapper` 연동 | Phase 1 완료 후 | 대기 |
| REQ-001 황대원 | `ToolExecutionRepository` 테이블 스키마 협의 + `StateManager` PostgreSQL fallback | Phase 3 전 | 대기 |

---

## 비기능 목표

| 항목 | 기준 |
|------|------|
| Tool 단일 호출 P95 | < 500ms (LLM/외부 API 제외) |
| State Manager 응답 | < 50ms (Redis hit) |
| credential 평문 유출 | 0건 — `try/finally`에서 반드시 `wipe()` |
| RAG Faithfulness | >= 0.9 (Ragas) |
| 테스트 커버리지 | >= 90% |

---

## 상세 플랜 파일 목록

| 파일 | 내용 |
|------|------|
| `req-005-phase0-schemas.md` | common-schemas 실제 구현 내용 + toolset 로컬 예외 |
| `req-005-phase1-domain.md` | Domain Layer 상세 구현 |
| `req-005-phase2-application.md` | Application Layer 상세 구현 (3개 유스케이스) |
| `req-005-phase3-adapters.md` | Adapter Core 상세 구현 |
| `req-005-phase4-tools.md` | 8개 Tool 상세 구현 |
| `req-005-phase5-tests.md` | 테스트 전체 코드 |
