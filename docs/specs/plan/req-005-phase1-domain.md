# Phase 1 — Domain Layer

> **대상 경로**: `modules/toolset/domain/`
> **핵심 규칙**: 프레임워크(FastAPI, SQLAlchemy, Celery, LangGraph) import 절대 금지
> **허용 import**: `common_schemas`, `abc`, `uuid`, `datetime`, `jsonschema`, stdlib
> **추가 허용**: `jsonschema` (순수 Python 라이브러리, 프레임워크 아님)

---

## 디렉토리 구조

```
domain/
├── exceptions.py              ← toolset 로컬 예외 (common_schemas에 없는 것들)
├── entities/
│   ├── __init__.py
│   ├── base_tool.py           ← BaseTool ABC
│   ├── tool_execution_record.py
│   └── tool_metadata.py
├── value_objects/
│   ├── __init__.py
│   ├── tool_input.py
│   ├── tool_output.py
│   └── execution_timeout.py
├── services/
│   ├── __init__.py
│   ├── runtime_validator.py
│   ├── tool_execution_service.py
│   └── risk_assessment_service.py
└── ports/
    ├── __init__.py
    ├── tool_registry.py
    ├── secure_connector_port.py
    └── tool_execution_repository.py
```

---

## 1-0. `domain/exceptions.py`

common_schemas에 없는 toolset 전용 예외 클래스들.

```python
from __future__ import annotations

from common_schemas.exceptions import DomainError


class ToolExecutionError(DomainError):
    """외부 API 호출 실패. HTTP 502로 매핑."""


class CredentialError(DomainError):
    """자격증명 획득/복호화 실패. HTTP 401로 매핑."""


class ConflictError(DomainError):
    """도구 중복 등록 등 충돌. HTTP 409로 매핑."""
```

**사용 예:**
```python
raise ToolExecutionError(
    message=f"Google Drive API failed: {e}",
    code="TOOL_EXECUTION_ERROR",
)
raise CredentialError(
    message=f"Failed to acquire credential '{cred_id}'",
    code="CREDENTIAL_ERROR",
)
```

---

## 1-1. `domain/entities/base_tool.py`

**역할**: 모든 Tool 구현체의 추상 기본 클래스.

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from common_schemas.enums import RiskLevel


class BaseTool(ABC):
    """모든 외부 도구의 추상 기본 클래스."""

    @property
    @abstractmethod
    def name(self) -> str:
        """도구 고유 이름."""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """도구 버전 (semver)."""
        ...

    @property
    @abstractmethod
    def risk_level(self) -> RiskLevel:
        """도구 위험도 등급."""
        ...

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """입력 JSON Schema 정의."""
        ...

    @property
    @abstractmethod
    def output_schema(self) -> dict[str, Any]:
        """출력 JSON Schema 정의."""
        ...

    @abstractmethod
    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        """
        도구 실행. RuntimeValidator가 호출 전후로 I/O를 검증한다.

        Raises:
            ToolExecutionError: 외부 API 호출 실패
        """
        ...
```

---

## 1-2. `domain/entities/tool_execution_record.py`

**역할**: 도구 실행 완료 후 이력을 저장하는 엔티티.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID, uuid4


@dataclass
class ToolExecutionRecord:
    """
    도구 실행 결과 이력 엔티티.

    ToolExecutionService가 생성, ToolExecutionRepository가 저장.
    """

    tool_name: str                              # 도구 이름 (str). 이력 조회 기준.
    input_data: dict
    status: Literal["success", "failed", "timeout"]
    duration_ms: int
    executed_at: datetime = field(default_factory=datetime.utcnow)
    execution_id: UUID = field(default_factory=uuid4)
    output_data: Optional[dict] = None
    error_message: Optional[str] = None

    def is_successful(self) -> bool:
        return self.status == "success"
```

---

## 1-3. `domain/entities/tool_metadata.py`

**역할**: 도구 카탈로그에서 조회할 때 사용하는 메타데이터 엔티티.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_schemas.enums import RiskLevel

if TYPE_CHECKING:
    from .base_tool import BaseTool


@dataclass(frozen=True)
class ToolMetadata:
    """
    도구 카탈로그 메타데이터.

    ToolRegistry에 저장되고 ListToolsUseCase가 반환하는 타입.
    """

    tool_id: UUID                           # 고유 식별자 (UUID)
    name: str
    version: str                            # semver. 예: "1.0.0"
    category: str                           # 예: "api", "file", "notification"
    description: str
    risk_level: RiskLevel
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    is_enabled: bool = True

    @classmethod
    def from_tool(
        cls,
        tool: BaseTool,
        tool_id: UUID,
        version: str,
        category: str,
    ) -> ToolMetadata:
        return cls(
            tool_id=tool_id,
            name=tool.name,
            version=version,
            category=category,
            description=tool.description,
            risk_level=tool.risk_level,
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
        )
```

---

## 1-4. `domain/value_objects/tool_input.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolInput:
    """
    RuntimeValidator를 통과한 검증된 도구 입력.
    불변(frozen) — 검증 후 변경 불가.
    """
    data: dict[str, Any]
    schema_version: str = "draft-7"
```

## 1-5. `domain/value_objects/tool_output.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolOutput:
    """
    RuntimeValidator를 통과한 검증된 도구 출력.
    불변(frozen) — 검증 후 변경 불가.
    """
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
```

## 1-6. `domain/value_objects/execution_timeout.py`

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionTimeout:
    """도구 실행 타임아웃 설정 VO."""
    seconds: int

    DEFAULT: int = 30   # 기본값 (환경변수 TOOL_EXECUTION_TIMEOUT 우선)
    MAX: int = 300      # 최대 허용값

    def __post_init__(self) -> None:
        if self.seconds <= 0:
            raise ValueError(f"Timeout must be positive, got {self.seconds}")
        if self.seconds > self.MAX:
            raise ValueError(f"Timeout {self.seconds}s exceeds MAX {self.MAX}s")
```

---

## 1-7. `domain/services/runtime_validator.py`

**역할**: 도구 실행 전/후 I/O 스키마 검증. `jsonschema.Draft7Validator` 사용.

```python
from __future__ import annotations

import jsonschema
import jsonschema.exceptions

from ..exceptions import ToolExecutionError
from common_schemas.exceptions import ValidationError


class RuntimeValidator:
    """
    도구 실행 시점의 입력/출력 JSON Schema 검증기.

    jsonschema.Draft7Validator로 검증.
    복수 오류를 모두 수집한 뒤 첫 번째 오류 메시지로 ValidationError 발생.

    QAEvaluatorService(REQ-004)와 역할 구분:
    - RuntimeValidator: 단일 도구 I/O 데이터 타입 구조 검증 (per-tool)
    - QAEvaluatorService: 전체 워크플로우 초안 품질 LLM 평가 (의미적 검증)
    """

    def validate_input(self, params: dict, schema: dict) -> ToolInput:
        """
        params가 tool.input_schema를 만족하는지 검증.

        Returns:
            검증 통과한 ToolInput
        Raises:
            ValidationError: 스키마 위반 시
        """
        self._validate(params, schema, prefix="input")
        return ToolInput(data=params)

    def validate_output(self, result: dict, schema: dict) -> ToolOutput:
        """
        result가 tool.output_schema를 만족하는지 검증.

        Returns:
            검증 통과한 ToolOutput
        Raises:
            ValidationError: 스키마 위반 시
        """
        self._validate(result, schema, prefix="output")
        return ToolOutput(data=result)

    def _validate(self, data: dict, schema: dict, prefix: str) -> None:
        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(data))

        if errors:
            first = errors[0]
            field_path = f"{prefix}.{'.'.join(str(p) for p in first.absolute_path) or 'root'}"
            raise ValidationError(
                message=f"[{field_path}] {first.message}",
                code="E_NODE_TYPE_MISMATCH",   # common_schemas.ErrorCode 중 가장 근접한 값
            )
```

---

## 1-8. `domain/services/risk_assessment_service.py`

**역할**: 도구 실행 전 위험도 검사. 순수 비즈니스 규칙, 외부 의존 없음.

```python
from __future__ import annotations

from common_schemas.exceptions import AuthorizationError
from common_schemas.security import PermissionSource

from ..entities.base_tool import BaseTool

# RiskLevel 비교 순서 (RiskLevel.value 값과 정확히 일치)
_RISK_ORDER = ["Low", "Medium", "High", "Restricted"]


class RiskAssessmentService:
    """
    도구 실행 전 위험도 검사 서비스.

    tool.risk_level이 permission_source.risk_ceiling을 초과하면 AuthorizationError 발생.

    risk_ceiling은 Literal["High", "Restricted"] — 두 값만 가능:
    - "High": LOW/MEDIUM/HIGH 도구 실행 가능, RESTRICTED 불가
    - "Restricted": 모든 도구 실행 가능
    """

    def assess(self, tool: BaseTool, context: PermissionSource) -> bool:
        """
        위험도 검사. 통과 시 True 반환.

        Returns:
            True (통과)
        Raises:
            AuthorizationError: tool.risk_level > context.risk_ceiling
        """
        tool_idx = _RISK_ORDER.index(tool.risk_level.value)
        ceiling_idx = _RISK_ORDER.index(context.risk_ceiling)

        if tool_idx > ceiling_idx:
            raise AuthorizationError(
                message=(
                    f"Tool '{tool.name}' requires risk level '{tool.risk_level.value}', "
                    f"but user's ceiling is '{context.risk_ceiling}'."
                ),
                code="E_PERMISSION_DENIED",
            )
        return True
```

---

## 1-9. `domain/services/tool_execution_service.py`

**역할**: 검증 → 실행 → 검증 파이프라인 오케스트레이션 (credential 처리 제외).

```python
from __future__ import annotations

from common_schemas.security import PlaintextCredential

from ..entities.base_tool import BaseTool
from ..exceptions import ToolExecutionError
from .runtime_validator import RuntimeValidator


class ToolExecutionService:
    """
    BaseTool 실행 오케스트레이션 서비스.

    파이프라인: validate_input → tool.run() → validate_output

    credential lifecycle(acquire/wipe/release)은
    ExecuteToolUseCase에서 관리하므로 여기서는 담당하지 않는다.
    """

    def __init__(self, validator: RuntimeValidator) -> None:
        self._validator = validator

    async def execute(
        self,
        tool: BaseTool,
        params: dict,
        credential: PlaintextCredential | None = None,
    ) -> dict:
        """
        단일 도구를 실행하고 검증된 결과를 반환한다.

        Raises:
            ValidationError: 입력/출력 스키마 위반
            ToolExecutionError: 외부 API 호출 실패
        """
        self._validator.validate_input(params, tool.input_schema)

        try:
            result = await tool.execute(params, credential=credential)
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(
                message=f"Tool '{tool.name}' execution failed: {e}",
                code="TOOL_EXECUTION_ERROR",
            ) from e

        self._validator.validate_output(result, tool.output_schema)
        return result
```

---

## 1-10. `domain/ports/tool_registry.py`

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from ..entities.base_tool import BaseTool
from ..entities.tool_metadata import ToolMetadata


class ToolRegistry(ABC):
    """도구 등록 및 조회 Port. 구현체: adapters/tool_registry_adapter.py"""

    @abstractmethod
    def get(self, tool_name: str) -> BaseTool:
        """
        Raises:
            NotFoundError: tool_name 미등록
        """
        ...

    @abstractmethod
    def list_all(self) -> list[ToolMetadata]:
        """등록된 전체 도구 메타데이터 목록."""
        ...

    @abstractmethod
    def list_by_category(self, category: str) -> list[ToolMetadata]:
        """특정 카테고리 도구 메타데이터 목록."""
        ...

```

> ⚠️ `register_tool()`은 Port ABC에 포함하지 않음.
> 도구 등록은 DI 조립 시점의 adapter 전용 책임 → `ToolRegistryAdapter.register_tool()` 참조.

---

## 1-11. `domain/ports/secure_connector_port.py`

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from common_schemas.security import PlaintextCredential

from ..value_objects.connector_response import ConnectorResponse


class SecureConnectorPort(ABC):
    """외부 엔드포인트에 자격증명을 주입해 HTTP 요청을 수행하는 Port.

    구현체: adapters/secure_connector.py (auth.CredentialInjectionService 연동)
    adapter에서 httpx.Response → ConnectorResponse 변환 책임.
    domain 레이어는 httpx에 직접 의존하지 않음.
    """

    @abstractmethod
    async def connect(
        self,
        endpoint: str,
        credentials: PlaintextCredential,
        **kwargs,
    ) -> ConnectorResponse: ...
```

---

## 1-12. `domain/ports/tool_execution_repository.py`

```python
from __future__ import annotations

from abc import ABC, abstractmethod

from ..entities.tool_execution_record import ToolExecutionRecord


class ToolExecutionRepository(ABC):
    """
    도구 실행 이력 저장 Port.
    구현체: modules/storage/repositories/ (REQ-001 황대원)

    협의 필요: 저장 테이블 스키마 확정 후 구현 진행 (req-005-overview.md 참고)
    """

    @abstractmethod
    async def save(self, record: ToolExecutionRecord) -> None:
        """실행 이력 저장."""
        ...

    @abstractmethod
    async def find_by_tool(
        self,
        tool_name: str,
        limit: int = 100,
    ) -> list[ToolExecutionRecord]:
        """특정 도구의 최근 실행 이력 조회."""
        ...
```

---

## 1-13. `__init__.py` 파일들

### `domain/entities/__init__.py`
```python
from .base_tool import BaseTool
from .tool_execution_record import ToolExecutionRecord
from .tool_metadata import ToolMetadata

__all__ = ["BaseTool", "ToolExecutionRecord", "ToolMetadata"]
```

### `domain/value_objects/__init__.py`
```python
from .tool_input import ToolInput
from .tool_output import ToolOutput
from .execution_timeout import ExecutionTimeout

__all__ = ["ToolInput", "ToolOutput", "ExecutionTimeout"]
```

### `domain/services/__init__.py`
```python
from .runtime_validator import RuntimeValidator
from .tool_execution_service import ToolExecutionService
from .risk_assessment_service import RiskAssessmentService

__all__ = ["RuntimeValidator", "ToolExecutionService", "RiskAssessmentService"]
```

### `domain/ports/__init__.py`
```python
from .tool_registry import ToolRegistry
from .secure_connector_port import SecureConnectorPort
from .tool_execution_repository import ToolExecutionRepository

__all__ = ["ToolRegistry", "SecureConnectorPort", "ToolExecutionRepository"]
```

---

## 확인 체크리스트

- [ ] `exceptions.py`: `ToolExecutionError`, `CredentialError`, `ConflictError` 정의
- [ ] `base_tool.py`: `__init_subclass__` 검증 — 필수 6개 변수 누락 시 `TypeError`
- [ ] `base_tool.py`: `run()` 시그니처 `async`, `PlaintextCredential | None`
- [ ] `tool_execution_record.py`: `status` Literal 타입 확인
- [ ] `runtime_validator.py`: `Draft7Validator` 사용 (not `jsonschema.validate`)
- [ ] `runtime_validator.py`: 오류 field path — `"{prefix}.{path or 'root'}"` 형식
- [ ] `risk_assessment_service.py`: `_RISK_ORDER = ["Low", "Medium", "High", "Restricted"]`
- [ ] `risk_assessment_service.py`: `context.risk_ceiling`은 `str` 타입 (`"High"` or `"Restricted"`)
- [ ] `secure_connector_port.py`: `connect(endpoint, credentials) -> ConnectorResponse` 인터페이스
- [ ] 프레임워크 import 없음 (ruff lint 통과)
