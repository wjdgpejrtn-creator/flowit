# Phase 0 — common-schemas 실제 구현 (REQ-012 완료)

> **상태**: ✅ DONE — PR #11 (`feature/req-012-common-schemas` → `development`) merge 완료
> **담당**: 황대원 (REQ-012), 이가원은 수정 불가 — import만 사용
> **실제 파일 위치**: `packages/common-schemas/python/common_schemas/`

---

## 주의: 플랜에서 예상했던 것과 실제 구현이 다름

플랜에서 가정했던 내용과 실제 구현된 내용의 **핵심 차이**를 반드시 숙지하고 Phase 1~5 구현 시 적용할 것.

---

## 실제 구현된 파일들

### `enums.py` — 실제 구현

```python
from enum import Enum


class AgentMode(str, Enum):
    ONBOARDING = "onboarding"
    WIZARD = "wizard"
    EDIT = "edit"
    GENERAL = "general"
    SECURITY = "security"


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    # ⚠️ PENDING, CANCELLED, SUCCESS 없음


class RiskLevel(str, Enum):
    LOW = "Low"         # ⚠️ 소문자 아님! 대소문자 혼합
    MEDIUM = "Medium"
    HIGH = "High"
    RESTRICTED = "Restricted"  # ⚠️ CRITICAL 아님


class ErrorCode(str, Enum):
    # ⚠️ HTTP 상태코드 기반 아님 — 노드/그래프 검증 코드
    E_NODE_TYPE_MISMATCH = "E_NODE_TYPE_MISMATCH"
    E_CYCLE_DETECTED = "E_CYCLE_DETECTED"
    E_ISOLATED_NODE = "E_ISOLATED_NODE"
    E_DUPLICATE_ID = "E_DUPLICATE_ID"
    E_PERMISSION_DENIED = "E_PERMISSION_DENIED"
    E_MISSING_CONNECTION = "E_MISSING_CONNECTION"
    E_INVALID_TRIGGER = "E_INVALID_TRIGGER"
    # ⚠️ TOOL_EXECUTION_ERROR, NOT_FOUND, CREDENTIAL_ERROR 등 없음
```

**핵심 차이점:**
- `RiskLevel` 값이 `"low"` 아니라 `"Low"` — 대소문자 구분 주의
- `RESTRICTED` (기존 플랜은 `CRITICAL`)
- `ErrorCode`는 그래프 검증용 코드 — toolset 전용 코드 없음

---

### `security.py` — 실제 구현

```python
from __future__ import annotations
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class PermissionSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    role: Literal["User", "Admin"]           # ⚠️ "admin"/"member" 아님
    department_id: UUID                       # ⚠️ str 아님, UUID
    session_id: UUID
    current_workflow_id: Optional[UUID] = None
    current_skill_id: Optional[UUID] = None
    granted_scopes: list[Literal["Private", "Team", "Public"]]  # ⚠️ OAuth scope 아님
    risk_ceiling: Literal["High", "Restricted"]  # ⚠️ RiskLevel 타입 아님, 문자열 리터럴


class PlaintextCredential(BaseModel):
    model_config = ConfigDict(frozen=False)

    credential_id: str                        # ⚠️ UUID 아님, str
    credential_kind: Literal["fernet", "aes_gcm"]
    value: str                                # ⚠️ token 아님, value

    def wipe(self) -> None:
        self.value = ""                       # ⚠️ bytearray 방식 아님, 단순 빈 문자열
```

**핵심 차이점:**
| 항목 | 플랜 예상 | 실제 구현 |
|------|----------|----------|
| `risk_ceiling` 타입 | `RiskLevel` enum | `Literal["High", "Restricted"]` |
| `granted_scopes` 내용 | OAuth scope URL 리스트 | `["Private", "Team", "Public"]` 리터럴 |
| `credential_id` 타입 | `UUID` | `str` |
| credential 필드명 | `token` | `value` |
| `credential_kind` | 없음 | `"fernet"` \| `"aes_gcm"` |
| `wipe()` 방식 | `object.__setattr__` bytearray | `self.value = ""` 단순 초기화 |

---

### `exceptions.py` — 실제 구현

```python
class DomainError(Exception):
    def __init__(self, message: str = "", *, code: str | None = None):
        self.code = code
        super().__init__(message)


class ValidationError(DomainError):
    pass

class AuthorizationError(DomainError):
    pass

class ExecutionError(DomainError):
    pass

class NotFoundError(DomainError):
    pass
```

**핵심 차이점:**
- `DomainError.__init__` 시그니처: `(message, *, code: str|None)` — code가 keyword-only
- `ToolExecutionError` 없음 → `ExecutionError` 사용 또는 toolset 로컬 정의
- `CredentialError` 없음 → toolset 로컬 정의
- `ConflictError` 없음 → toolset 로컬 정의
- `code` 필드는 `ErrorCode` enum이 아니라 `str | None`

---

### `validation.py` — 실제 구현

```python
from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict
from .enums import ErrorCode


class ValidationErrorItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: ErrorCode                          # ⚠️ ErrorCode는 그래프 검증 코드
    message: str
    node_ids: list[str]
    edge_id: Optional[str] = None
    validator: Literal["SchemaValidation", "RuntimeValidation"]
    hint: Optional[str] = None


class ValidationErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    validation_status: Literal["passed", "failed"]
    errors: list[ValidationErrorItem]
```

**핵심 차이점:**
- `ValidationErrorItem`은 노드 그래프 검증용 구조 — toolset I/O 검증에는 직접 사용 부적합
- toolset `RuntimeValidator`는 단순 `jsonschema` 오류 메시지를 toolset 로컬 예외로 변환

---

## toolset 로컬 예외 정의 (Phase 1에서 구현)

common_schemas에 없는 예외들은 `modules/toolset/domain/exceptions.py`에 직접 정의:

```python
# modules/toolset/domain/exceptions.py
from common_schemas.exceptions import DomainError


class ToolExecutionError(DomainError):
    """외부 API 호출 실패 (HTTP 502)."""


class CredentialError(DomainError):
    """자격증명 획득/복호화 실패 (HTTP 401)."""


class ConflictError(DomainError):
    """도구 중복 등록 등 충돌 (HTTP 409)."""
```

**사용 방법:**
```python
raise ToolExecutionError(
    message=f"Tool '{tool_id}' execution failed: {e}",
    code="TOOL_EXECUTION_ERROR",   # code는 str
)
raise CredentialError(
    message=f"Failed to acquire credential '{credential_id}': {e}",
    code="CREDENTIAL_ERROR",
)
```

---

## risk_ceiling 비교 로직 (수정된 방식)

`risk_ceiling`이 `RiskLevel` enum이 아니라 `Literal["High", "Restricted"]`이므로:

```python
_RISK_ORDER = ["Low", "Medium", "High", "Restricted"]

def _check_permission(tool: BaseTool, permission_source: PermissionSource) -> None:
    tool_idx = _RISK_ORDER.index(tool.risk_level.value)          # RiskLevel enum → str
    ceiling_idx = _RISK_ORDER.index(permission_source.risk_ceiling)  # 이미 str
    if tool_idx > ceiling_idx:
        raise AuthorizationError(
            message=f"Tool '{tool.tool_id}' requires '{tool.risk_level.value}', "
                    f"ceiling is '{permission_source.risk_ceiling}'.",
            code="E_PERMISSION_DENIED",
        )
```

---

## 올바른 import 경로 요약

```python
# enums
from common_schemas.enums import RiskLevel, ExecutionStatus, ErrorCode

# security
from common_schemas.security import PermissionSource, PlaintextCredential

# exceptions (공통)
from common_schemas.exceptions import (
    DomainError, ValidationError, AuthorizationError,
    ExecutionError, NotFoundError,
)

# toolset 로컬 예외 (modules/toolset/domain/exceptions.py)
from ..domain.exceptions import ToolExecutionError, CredentialError, ConflictError
```

---

## 확인 체크리스트

- [x] PR #11 merge 완료 → development 브랜치에서 실제 파일 확인 완료
- [ ] Phase 1 구현 시 `RiskLevel` 값이 `"Low"`, `"Medium"`, `"High"`, `"Restricted"` 임을 코드에 반영
- [ ] `PermissionSource.risk_ceiling`이 `str` 타입임을 `_check_permission` 로직에 반영
- [ ] `PlaintextCredential.value` (`.token` 아님) 필드명 전체 코드 적용
- [ ] `domain/exceptions.py`에 toolset 로컬 예외 3개 정의
- [ ] REQ-002 박아름에게 `CredentialInjectionService.inject(credential_id, node_id)` — `node_id` 활용 방식 확인
