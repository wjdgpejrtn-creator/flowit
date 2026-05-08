# Phase 2 — Application Layer

> **대상 경로**: `modules/toolset/application/use_cases/`
> **핵심 규칙**: Port(ABC) 인터페이스를 통해서만 외부 접근. 구현체 직접 import 금지.
> **허용 import**: `domain/*`, `common_schemas`

---

## 유스케이스 목록

| 유스케이스 | 파일명 | 역할 |
|-----------|--------|------|
| `ExecuteToolUseCase` | `execute_tool_use_case.py` | 단일 도구 실행 메인 파이프라인 |
| `ListToolsUseCase` | `list_tools_use_case.py` | 도구 카탈로그 조회 (API 서버용) |
| `ValidateToolConfigUseCase` | `validate_tool_config_use_case.py` | 설정 사전 검증 (드래프트 단계) |

---

## 2-1. `application/use_cases/execute_tool_use_case.py`

**역할**: 도구 실행 메인 오케스트레이션.
파이프라인: 권한 검사 → 입력 검증 → Credential 획득 → 실행 → 출력 검증 → 이력 저장 → Credential 폐기

```python
from __future__ import annotations

import time
from datetime import datetime

from common_schemas.exceptions import AuthorizationError
from common_schemas.security import PermissionSource, PlaintextCredential

from ...domain.entities.tool_execution_record import ToolExecutionRecord
from ...domain.exceptions import CredentialError, ToolExecutionError
from ...domain.ports.secure_connector_port import SecureConnectorPort
from ...domain.ports.tool_execution_repository import ToolExecutionRepository
from ...domain.ports.tool_registry import ToolRegistry
from ...domain.services.risk_assessment_service import RiskAssessmentService
from ...domain.services.runtime_validator import RuntimeValidator


class ExecuteToolUseCase:
    """
    도구 실행 유스케이스.

    실행 파이프라인:
    1. ToolRegistry에서 도구 조회
    2. RiskAssessmentService.assess() — 권한/위험도 검사
    3. RuntimeValidator.validate_input() — 입력 스키마 검증
    4. SecureConnectorPort.connect() — 자격증명 주입 HTTP 요청 (credential_id 있을 때만)
    5. BaseTool.execute() — 도구 실행
    6. RuntimeValidator.validate_output() — 출력 스키마 검증
    7. ToolExecutionRepository.save() — 실행 이력 저장
    8. [finally] credential.wipe() — 자격증명 즉시 폐기

    DI 조립 위치: services/api_server/app/dependencies/tools.py
    호출 주체: services/execution_engine (REQ-007)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        secure_connector: SecureConnectorPort,
        validator: RuntimeValidator,
        risk_service: RiskAssessmentService,
        execution_repo: ToolExecutionRepository,
    ) -> None:
        self._registry = tool_registry
        self._connector = secure_connector
        self._validator = validator
        self._risk = risk_service
        self._repo = execution_repo

    async def execute(
        self,
        tool_name: str,
        input_data: dict,
        context: PermissionSource,
        credential_id: str | None = None,
    ) -> dict:
        """
        도구를 실행하고 검증된 결과를 반환한다.

        Args:
            tool_name: 실행할 도구 이름 (예: "google_drive")
            input_data: 도구 입력 파라미터 (raw dict, 검증 전)
            context: 요청자 권한 컨텍스트 (JWT에서 추출한 PermissionSource)
            credential_id: OAuth 자격증명 ID. 인증 불필요 도구는 None.

        Returns:
            output_schema를 만족하는 결과 딕셔너리

        Raises:
            NotFoundError: tool_name 미등록
            AuthorizationError: risk_ceiling 초과
            ValidationError: 입력/출력 스키마 위반
            ToolExecutionError: 외부 API 호출 실패
            CredentialError: 자격증명 획득 실패
        """
        # 1. 도구 조회
        tool = self._registry.get(tool_name)

        # 2. 권한 검사
        self._risk.assess(tool, context)

        # 3. 입력 스키마 검증
        self._validator.validate_input(input_data, tool.input_schema)

        # 4. Credential 획득 (credential_id 있을 때만)
        # SecureConnectorPort.connect()는 tool.execute() 내부에서 직접 호출됨.
        # use case는 PlaintextCredential을 CredentialInjectionService(auth)로 조회해 tool에 전달.
        credential: PlaintextCredential | None = None
        if credential_id is not None:
            credential = await self._connector.connect(
                endpoint="",  # credential 조회 전용 호출 시 빈 endpoint
                credentials=PlaintextCredential(value=credential_id, credential_kind="lookup"),
            )
            # ⚠️ Phase 2 구현 시 확정 필요:
            # auth.CredentialInjectionService.inject(credential_id, node_id) → PlaintextCredential
            # 로 대체 예정 (SecureConnectorPort는 실제 HTTP 요청용)

        start_ms = time.monotonic()
        status = "failed"
        error_msg: str | None = None
        result: dict = {}

        try:
            # 5. 도구 실행 (connector를 kwargs로 전달 — tool이 필요 시 connect() 호출)
            result = await tool.execute(input_data, credential=credential, connector=self._connector)

            # 6. 출력 스키마 검증
            self._validator.validate_output(result, tool.output_schema)
            status = "success"
            return result

        except (AuthorizationError, ToolExecutionError, CredentialError):
            raise

        except Exception as e:
            error_msg = str(e)
            raise ToolExecutionError(
                message=f"Tool '{tool_name}' execution failed: {e}",
                code="TOOL_EXECUTION_ERROR",
            ) from e

        finally:
            duration_ms = int((time.monotonic() - start_ms) * 1000)

            # 7. 실행 이력 저장 (best-effort — 실패해도 예외 전파 안 함)
            try:
                record = ToolExecutionRecord(
                    tool_name=tool_name,
                    input_data=input_data,
                    output_data=result if status == "success" else None,
                    status=status,
                    duration_ms=duration_ms,
                    executed_at=datetime.utcnow(),
                    error_message=error_msg,
                )
                await self._repo.save(record)
            except Exception:
                pass  # 이력 저장 실패는 도구 실행 결과에 영향 없음

            # 8. Credential 즉시 폐기 (성공/실패 무관)
            if credential is not None:
                credential.wipe()
```

### 실행 흐름 다이어그램

```
execute(tool_name, input_data, context, credential_id)
│
├─ registry.get(tool_name)                              → NotFoundError 가능
├─ risk_service.assess(tool, context)                   → AuthorizationError 가능
├─ validator.validate_input(input_data, schema)         → ValidationError 가능
├─ [credential_id != None] credential 조회              → CredentialError 가능
│
├─ tool.execute(input_data, credential=..., connector=..) → ToolExecutionError 가능 (래핑)
│   └─ tool 내부에서 connector.connect(endpoint, credential) 호출 → ConnectorResponse
├─ validator.validate_output(result, schema)            → ValidationError 가능
│
└─ [finally]
    ├─ repo.save(record)                                ← best-effort (예외 무시)
    └─ credential.wipe()                                ← 항상 실행
```

### 엣지 케이스

| 케이스 | 처리 방식 |
|--------|----------|
| `credential_id=None` (webhook, delay 등) | credential 조회 건너뜀, `credential=None`으로 `execute()` 호출 |
| `tool.execute()`에서 비도메인 예외 | `ToolExecutionError`로 래핑 후 재발생 |
| `connector.connect()` 실패 | `ToolExecutionError` 발생 — tool 내부에서 처리 |
| `validate_output()` 실패 | `ValidationError` 발생. credential은 이미 finally에서 wipe |
| `repo.save()` 실패 | best-effort — 이력 저장 실패해도 결과는 그대로 반환 |

---

## 2-2. `application/use_cases/list_tools_use_case.py`

**역할**: 도구 카탈로그 조회. API 서버의 `GET /api/v1/tools` 엔드포인트에서 호출.

```python
from __future__ import annotations

from common_schemas.enums import RiskLevel

from ...domain.entities.tool_metadata import ToolMetadata
from ...domain.ports.tool_registry import ToolRegistry


class ListToolsUseCase:
    """
    도구 카탈로그 조회 유스케이스.

    호출 주체: services/api_server (REQ-009)
    용도: 사용자가 워크플로우 편집기에서 사용 가능한 도구 목록을 볼 때
    """

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self._registry = tool_registry

    def execute(
        self,
        category: str | None = None,
        risk_level: RiskLevel | None = None,
    ) -> list[ToolMetadata]:
        """
        등록된 도구 메타데이터 목록을 반환.

        Args:
            category: 필터 — 특정 카테고리만 반환. None이면 전체 반환.
            risk_level: 필터 — 특정 위험 등급만 반환. None이면 전체 반환.

        Returns:
            ToolMetadata 목록 (is_enabled=True인 것만)
        """
        if category is not None:
            metadata_list = self._registry.list_by_category(category)
        else:
            metadata_list = self._registry.list_all()

        if risk_level is not None:
            metadata_list = [m for m in metadata_list if m.risk_level == risk_level]

        return [m for m in metadata_list if m.is_enabled]
```

---

## 2-3. `application/use_cases/validate_tool_config_use_case.py`

**역할**: 드래프트 단계에서 도구 설정 미리 검증. 워크플로우 저장 전 `BaseTool.input_schema` 기준 검사.

```python
from __future__ import annotations

from ...domain.ports.tool_registry import ToolRegistry
from ...domain.services.runtime_validator import RuntimeValidator


class ValidateToolConfigUseCase:
    """
    도구 설정 사전 검증 유스케이스.

    워크플로우 드래프트 저장 시 각 노드의 파라미터가
    해당 도구의 input_schema에 맞는지 미리 검증한다.

    실제 실행(credential 획득, API 호출)은 하지 않음.
    호출 주체: services/api_server (워크플로우 저장 API)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        validator: RuntimeValidator,
    ) -> None:
        self._registry = tool_registry
        self._validator = validator

    def execute(self, tool_name: str, parameters: dict) -> bool:
        """
        도구 파라미터 유효성 검증.

        Args:
            tool_name: 검증 대상 도구 이름
            parameters: 검증할 파라미터 딕셔너리

        Returns:
            True (유효), False 대신 예외 발생

        Raises:
            NotFoundError: tool_name 미등록
            ValidationError: 파라미터가 input_schema 위반
        """
        tool = self._registry.get(tool_name)
        self._validator.validate_input(parameters, tool.input_schema)
        return True
```

---

## 2-4. `application/use_cases/__init__.py`

```python
from .execute_tool_use_case import ExecuteToolUseCase
from .list_tools_use_case import ListToolsUseCase
from .validate_tool_config_use_case import ValidateToolConfigUseCase

__all__ = ["ExecuteToolUseCase", "ListToolsUseCase", "ValidateToolConfigUseCase"]
```

## 2-5. `application/__init__.py`

```python
from .use_cases import ExecuteToolUseCase, ListToolsUseCase, ValidateToolConfigUseCase

__all__ = ["ExecuteToolUseCase", "ListToolsUseCase", "ValidateToolConfigUseCase"]
```

---

## DI 조립 예시 (services/api_server)

```python
# services/api_server/app/dependencies/tools.py

from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter
from toolset.adapters.secure_connector import SecureConnector
from toolset.adapters.tools.google_drive_tool import GoogleDriveTool
from toolset.adapters.tools.gmail_tool import GmailTool
# ... 나머지 6개

from toolset.application.use_cases import (
    ExecuteToolUseCase,
    ListToolsUseCase,
    ValidateToolConfigUseCase,
)
from toolset.domain.services import (
    RuntimeValidator,
    RiskAssessmentService,
)

def create_execute_tool_use_case(
    inject_credential_svc,  # auth.domain.services.CredentialInjectionService
    execution_repo,         # storage.repositories.ToolExecutionRepository 구현체
) -> ExecuteToolUseCase:
    registry = ToolRegistryAdapter()
    registry.register_tool(GoogleDriveTool(), tool_id=uuid4(), category="google")
    registry.register_tool(GmailTool(), tool_id=uuid4(), category="google")
    # ... 8개 등록

    return ExecuteToolUseCase(
        tool_registry=registry,
        secure_connector=SecureConnector(inject_credential_svc),
        validator=RuntimeValidator(),
        risk_service=RiskAssessmentService(),
        execution_repo=execution_repo,
    )
```

---

## 확인 체크리스트

- [ ] `execute_tool_use_case.py`: `finally` 블록에서 `credential.wipe()` 보장
- [ ] `execute_tool_use_case.py`: 비도메인 예외 → `ToolExecutionError` 래핑
- [ ] `execute_tool_use_case.py`: `credential_id=None`일 때 `connector.connect()` 호출 안 함
- [ ] `execute_tool_use_case.py`: `repo.save()` best-effort (예외 무시)
- [ ] `list_tools_use_case.py`: `category` 필터 + `is_enabled=False` 필터링
- [ ] `validate_tool_config_use_case.py`: 실제 API 호출 없이 스키마 검증만
- [ ] 구현체 직접 import 없음 (Port만 참조)
