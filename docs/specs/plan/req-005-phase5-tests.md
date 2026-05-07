# Phase 5 — Tests

> **대상 경로**: `modules/toolset/tests/`
> **테스트 전략**: Domain/Application은 mock 기반 단위 테스트. Adapter는 통합 테스트(별도 진행).
> **도구**: `pytest`, `pytest-asyncio`, `unittest.mock`

---

## 테스트 디렉토리 구조

```
modules/toolset/tests/
├── conftest.py                              ← 공통 fixture
├── unit/
│   ├── domain/
│   │   ├── test_base_tool.py                ← BaseTool 검증
│   │   ├── test_runtime_validator.py        ← RuntimeValidator 검증
│   │   ├── test_risk_assessment_service.py  ← RiskAssessmentService 검증
│   │   └── test_tool_execution_service.py   ← ToolExecutionService 검증
│   └── application/
│       ├── test_execute_tool_use_case.py    ← ExecuteToolUseCase 검증
│       ├── test_list_tools_use_case.py      ← ListToolsUseCase 검증
│       └── test_validate_tool_config_use_case.py
└── integration/
    └── test_secure_connector.py             ← (별도 진행, 실제 auth 필요)
```

---

## `tests/conftest.py`

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from common_schemas.enums import RiskLevel
from common_schemas.security import PermissionSource, PlaintextCredential

from toolset.domain.base_tool import BaseTool
from toolset.domain.entities.tool_metadata import ToolMetadata
from toolset.domain.ports.tool_registry import ToolRegistry
from toolset.domain.ports.secure_connector_port import SecureConnectorPort
from toolset.domain.ports.tool_execution_repository import ToolExecutionRepository
from toolset.domain.services.runtime_validator import RuntimeValidator
from toolset.domain.services.risk_assessment_service import RiskAssessmentService


# ── 구체 Tool 구현체 (테스트용 더미) ──────────────────────────────────────

class DummyTool(BaseTool):
    """MEDIUM 위험도 테스트용 Tool."""
    name = "dummy"
    description = "테스트용 도구"
    version = "1.0.0"
    risk_level = RiskLevel.MEDIUM
    input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    output_schema = {
        "type": "object",
        "properties": {"result": {"type": "string"}},
        "required": ["result"],
    }

    async def execute(self, input_data: dict, **kwargs) -> dict:
        return {"result": f"ok: {input_data['message']}"}


class HighRiskDummyTool(BaseTool):
    """HIGH 위험도 테스트용 Tool."""
    name = "high_risk_dummy"
    description = "HIGH 위험도 테스트용"
    version = "1.0.0"
    risk_level = RiskLevel.HIGH
    input_schema = {"type": "object", "properties": {}}
    output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    async def execute(self, input_data: dict, **kwargs) -> dict:
        return {"ok": True}


class RestrictedDummyTool(BaseTool):
    """RESTRICTED 위험도 테스트용 Tool."""
    name = "restricted_dummy"
    description = "RESTRICTED 위험도 테스트용"
    version = "1.0.0"
    risk_level = RiskLevel.RESTRICTED
    input_schema = {"type": "object", "properties": {}}
    output_schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    async def execute(self, input_data: dict, **kwargs) -> dict:
        return {"ok": True}


# ── PermissionSource fixture ───────────────────────────────────────────────

@pytest.fixture
def permission_source_high():
    """risk_ceiling="High" 사용자."""
    return PermissionSource(
        user_id=uuid4(),
        role="User",
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling="High",              # Literal["High", "Restricted"]
    )


@pytest.fixture
def permission_source_restricted():
    """risk_ceiling="Restricted" 사용자."""
    return PermissionSource(
        user_id=uuid4(),
        role="Admin",
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private", "Team", "Public"],
        risk_ceiling="Restricted",
    )


# ── PlaintextCredential fixture ────────────────────────────────────────────

@pytest.fixture
def mock_credential():
    """테스트용 PlaintextCredential."""
    return PlaintextCredential(
        credential_id="test-cred-001",    # str 타입
        credential_kind="fernet",          # Literal["fernet", "aes_gcm"]
        value="test-oauth-token",          # ⚠️ .value 필드 (token 아님)
    )


# ── Port Mock fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def mock_tool_registry():
    """ToolRegistry mock."""
    from uuid import uuid4
    registry = MagicMock(spec=ToolRegistry)
    registry.get.return_value = DummyTool()
    registry.list_all.return_value = [ToolMetadata.from_tool(DummyTool(), tool_id=uuid4(), category="test")]
    registry.list_by_category.return_value = []
    return registry


@pytest.fixture
def mock_secure_connector():
    """SecureConnectorPort mock."""
    connector = AsyncMock(spec=SecureConnectorPort)
    return connector


@pytest.fixture
def mock_execution_repo():
    """ToolExecutionRepository mock."""
    repo = AsyncMock(spec=ToolExecutionRepository)
    return repo


# ── Domain service fixtures ────────────────────────────────────────────────

@pytest.fixture
def validator():
    return RuntimeValidator()


@pytest.fixture
def risk_service():
    return RiskAssessmentService()
```

---

## `tests/unit/domain/test_base_tool.py`

```python
from __future__ import annotations

import pytest
from common_schemas.enums import RiskLevel
from common_schemas.security import PlaintextCredential

from toolset.domain.base_tool import BaseTool


class TestBaseToolAbstractInterface:
    """BaseTool ABC @property @abstractmethod 인터페이스 테스트."""

    def test_abstract_property_missing_raises_type_error(self):
        """abstract property 미구현 시 인스턴스 생성 불가."""
        with pytest.raises(TypeError):
            class BrokenTool(BaseTool):
                async def execute(self, input_data, **kwargs):
                    return {}
            BrokenTool()  # instantiation 시점에 TypeError

    def test_complete_subclass_no_error(self):
        """모든 abstract property + execute 구현 시 정상 생성."""
        class OkTool(BaseTool):
            name = "ok"
            description = "ok tool"
            version = "1.0.0"
            risk_level = RiskLevel.LOW
            input_schema = {"type": "object"}
            output_schema = {"type": "object"}
            async def execute(self, input_data, **kwargs):
                return {}
        tool = OkTool()
        assert tool.name == "ok"
        assert tool.version == "1.0.0"

    def test_risk_level_restricted_allowed(self):
        """RESTRICTED는 유효한 RiskLevel."""
        class RestrictedTool(BaseTool):
            name = "r"
            description = "d"
            version = "1.0.0"
            risk_level = RiskLevel.RESTRICTED
            input_schema = {"type": "object"}
            output_schema = {"type": "object"}
            async def execute(self, input_data, **kwargs):
                return {}
        tool = RestrictedTool()
        assert tool.risk_level == RiskLevel.RESTRICTED

    @pytest.mark.asyncio
    async def test_execute_returns_dict(self):
        from tests.conftest import DummyTool
        tool = DummyTool()
        result = await tool.execute({"message": "hello"})
        assert result == {"result": "ok: hello"}
```

---

## `tests/unit/domain/test_runtime_validator.py`

```python
from __future__ import annotations

import pytest
from common_schemas.exceptions import ValidationError

from toolset.domain.services.runtime_validator import RuntimeValidator


@pytest.fixture
def validator():
    return RuntimeValidator()


SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["name"],
}


class TestValidateInput:
    def test_valid_input_passes(self, validator):
        validator.validate_input({"name": "test", "count": 1}, SIMPLE_SCHEMA)

    def test_missing_required_raises_validation_error(self, validator):
        with pytest.raises(ValidationError):
            validator.validate_input({"count": 1}, SIMPLE_SCHEMA)

    def test_wrong_type_raises_validation_error(self, validator):
        with pytest.raises(ValidationError):
            validator.validate_input({"name": 123}, SIMPLE_SCHEMA)

    def test_error_field_path_format(self, validator):
        """오류 필드 경로가 'input.{field}' 형식인지 확인."""
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_input({"count": 1}, SIMPLE_SCHEMA)
        # message에 'input.' prefix 포함 확인
        assert "input." in exc_info.value.args[0]


class TestValidateOutput:
    def test_valid_output_passes(self, validator):
        validator.validate_output({"name": "result"}, SIMPLE_SCHEMA)

    def test_invalid_output_raises_validation_error(self, validator):
        with pytest.raises(ValidationError):
            validator.validate_output({}, SIMPLE_SCHEMA)

    def test_output_error_field_prefix(self, validator):
        with pytest.raises(ValidationError) as exc_info:
            validator.validate_output({}, SIMPLE_SCHEMA)
        assert "output." in exc_info.value.args[0]
```

---

## `tests/unit/domain/test_risk_assessment_service.py`

```python
from __future__ import annotations

import pytest
from uuid import uuid4
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import AuthorizationError
from common_schemas.security import PermissionSource

from toolset.domain.services.risk_assessment_service import RiskAssessmentService
from tests.conftest import DummyTool, HighRiskDummyTool, RestrictedDummyTool


@pytest.fixture
def service():
    return RiskAssessmentService()


def make_permission(ceiling: str) -> PermissionSource:
    return PermissionSource(
        user_id=uuid4(),
        role="User",
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling=ceiling,
    )


class TestRiskAssessment:
    def test_medium_tool_with_high_ceiling_passes(self, service):
        service.assess(DummyTool(), make_permission("High"))  # 예외 없음

    def test_high_tool_with_high_ceiling_passes(self, service):
        service.assess(HighRiskDummyTool(), make_permission("High"))

    def test_restricted_tool_with_high_ceiling_fails(self, service):
        with pytest.raises(AuthorizationError):
            service.assess(RestrictedDummyTool(), make_permission("High"))

    def test_restricted_tool_with_restricted_ceiling_passes(self, service):
        service.assess(RestrictedDummyTool(), make_permission("Restricted"))

    def test_authorization_error_message_contains_tool_id(self, service):
        with pytest.raises(AuthorizationError) as exc_info:
            service.assess(RestrictedDummyTool(), make_permission("High"))
        assert "restricted_dummy" in str(exc_info.value)
```

---

## `tests/unit/application/test_execute_tool_use_case.py`

```python
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from common_schemas.enums import RiskLevel
from common_schemas.exceptions import AuthorizationError, ValidationError
from common_schemas.security import PermissionSource, PlaintextCredential

from toolset.application.use_cases.execute_tool_use_case import ExecuteToolUseCase
from toolset.domain.exceptions import ToolExecutionError, CredentialError
from toolset.domain.services.runtime_validator import RuntimeValidator
from toolset.domain.services.risk_assessment_service import RiskAssessmentService


def make_permission(ceiling: str = "High") -> PermissionSource:
    return PermissionSource(
        user_id=uuid4(),
        role="User",
        department_id=uuid4(),
        session_id=uuid4(),
        granted_scopes=["Private"],
        risk_ceiling=ceiling,
    )


def make_use_case(
    tool_registry=None,
    secure_connector=None,
    validator=None,
    risk_service=None,
    execution_repo=None,
):
    from tests.conftest import DummyTool
    from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter

    if tool_registry is None:
        from uuid import uuid4
        reg = ToolRegistryAdapter()
        reg.register_tool(DummyTool(), tool_id=uuid4(), category="test")
        tool_registry = reg

    return ExecuteToolUseCase(
        tool_registry=tool_registry,
        secure_connector=secure_connector or AsyncMock(),
        validator=validator or RuntimeValidator(),
        risk_service=risk_service or RiskAssessmentService(),
        execution_repo=execution_repo or AsyncMock(),
    )


class TestExecuteToolSuccess:
    @pytest.mark.asyncio
    async def test_execute_without_credential(self):
        uc = make_use_case()
        result = await uc.execute(
            tool_name="dummy",
            input_data={"message": "hello"},
            context=make_permission("High"),
            credential_id=None,
        )
        assert result == {"result": "ok: hello"}

    @pytest.mark.asyncio
    async def test_execute_with_credential(self, mock_credential):
        connector = AsyncMock()
        connector.connect.return_value = mock_credential
        uc = make_use_case(secure_connector=connector)

        result = await uc.execute(
            tool_name="dummy",
            input_data={"message": "world"},
            context=make_permission("High"),
            credential_id="cred-001",
        )
        assert result["result"] == "ok: world"
        connector.connect.assert_called_once()


class TestCredentialLifecycle:
    @pytest.mark.asyncio
    async def test_credential_wiped_on_success(self, mock_credential):
        connector = AsyncMock()
        connector.connect.return_value = mock_credential
        uc = make_use_case(secure_connector=connector)

        await uc.execute("dummy", {"message": "x"}, make_permission("High"), "cred-001")

        # wipe()가 호출되어 value가 빈 문자열이 되어야 함
        assert mock_credential.value == ""

    @pytest.mark.asyncio
    async def test_credential_wiped_on_tool_error(self, mock_credential):
        """도구 실행 실패해도 credential은 반드시 wipe."""
        from tests.conftest import DummyTool

        class FailingTool(DummyTool):
            name = "failing"
            async def execute(self, input_data, **kwargs):
                raise ValueError("External API down")

        from uuid import uuid4
        from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter
        reg = ToolRegistryAdapter()
        reg.register_tool(FailingTool(), tool_id=uuid4(), category="test")

        connector = AsyncMock()
        connector.connect.return_value = mock_credential
        uc = make_use_case(tool_registry=reg, secure_connector=connector)

        with pytest.raises(ToolExecutionError):
            await uc.execute("failing", {"message": "x"}, make_permission("High"), "cred-001")

        # 실패해도 wipe 보장
        assert mock_credential.value == ""
        # release_credential() 제거됨 — connect()가 단일 호출로 처리


class TestPermissionGating:
    @pytest.mark.asyncio
    async def test_restricted_tool_with_high_ceiling_raises_authorization_error(self):
        from uuid import uuid4
        from tests.conftest import RestrictedDummyTool
        from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter
        reg = ToolRegistryAdapter()
        reg.register_tool(RestrictedDummyTool(), tool_id=uuid4(), category="test")
        uc = make_use_case(tool_registry=reg)

        with pytest.raises(AuthorizationError):
            await uc.execute(
                "restricted_dummy",
                {},
                make_permission("High"),  # ceiling=High, tool=Restricted → 거부
            )


class TestValidationError:
    @pytest.mark.asyncio
    async def test_invalid_input_raises_validation_error(self):
        uc = make_use_case()
        with pytest.raises(ValidationError):
            await uc.execute(
                "dummy",
                {"wrong_field": 123},  # required: message 누락
                make_permission("High"),
            )


class TestNonDomainExceptionWrapping:
    @pytest.mark.asyncio
    async def test_unexpected_exception_wrapped_as_tool_execution_error(self):
        from tests.conftest import DummyTool
        from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter

        class CrashTool(DummyTool):
            tool_id = "crash"
            async def execute(self, input_data, **kwargs):
                raise RuntimeError("unexpected crash")

        from uuid import uuid4
        reg = ToolRegistryAdapter()
        reg.register_tool(CrashTool(), tool_id=uuid4(), category="test")
        uc = make_use_case(tool_registry=reg)

        with pytest.raises(ToolExecutionError) as exc_info:
            await uc.execute("crash", {"message": "x"}, make_permission("High"))
        assert "unexpected crash" in str(exc_info.value)
```

---

## `tests/unit/application/test_list_tools_use_case.py`

```python
from __future__ import annotations

import pytest
from common_schemas.enums import RiskLevel

from toolset.application.use_cases.list_tools_use_case import ListToolsUseCase
from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter
from tests.conftest import DummyTool, HighRiskDummyTool, RestrictedDummyTool


@pytest.fixture
def registry_with_tools():
    from uuid import uuid4
    reg = ToolRegistryAdapter()
    reg.register_tool(DummyTool(), tool_id=uuid4(), category="test")           # MEDIUM
    reg.register_tool(HighRiskDummyTool(), tool_id=uuid4(), category="test")   # HIGH
    reg.register_tool(RestrictedDummyTool(), tool_id=uuid4(), category="test") # RESTRICTED
    return reg


class TestListToolsUseCase:
    def test_list_all_tools(self, registry_with_tools):
        uc = ListToolsUseCase(registry_with_tools)
        result = uc.execute()
        assert len(result) == 3

    def test_filter_by_risk_level(self, registry_with_tools):
        uc = ListToolsUseCase(registry_with_tools)
        result = uc.execute(risk_level=RiskLevel.HIGH)
        assert len(result) == 1
        assert result[0].risk_level == RiskLevel.HIGH

    def test_empty_result_for_nonexistent_risk_level(self, registry_with_tools):
        uc = ListToolsUseCase(registry_with_tools)
        result = uc.execute(risk_level=RiskLevel.LOW)
        assert result == []
```

---

## `tests/unit/domain/test_tool_execution_service.py`

```python
from __future__ import annotations

import pytest
from common_schemas.exceptions import ValidationError

from toolset.domain.services.tool_execution_service import ToolExecutionService
from toolset.domain.services.runtime_validator import RuntimeValidator
from toolset.domain.exceptions import ToolExecutionError
from tests.conftest import DummyTool


@pytest.fixture
def service():
    return ToolExecutionService(RuntimeValidator())


class TestToolExecutionService:
    @pytest.mark.asyncio
    async def test_valid_execution_returns_result(self, service):
        result = await service.execute(DummyTool(), {"message": "test"})
        assert result == {"result": "ok: test"}

    @pytest.mark.asyncio
    async def test_invalid_input_raises_validation_error(self, service):
        with pytest.raises(ValidationError):
            await service.execute(DummyTool(), {})

    @pytest.mark.asyncio
    async def test_runtime_exception_wrapped_as_tool_execution_error(self, service):
        from tests.conftest import DummyTool as Base

        class CrashTool(Base):
            tool_id = "crash2"
            async def execute(self, input_data, **kwargs):
                raise ConnectionError("network down")

        with pytest.raises(ToolExecutionError) as exc_info:
            await service.execute(CrashTool(), {"message": "x"})
        assert "network down" in str(exc_info.value)
```

---

## 확인 체크리스트

- [ ] `conftest.py`: `PermissionSource(risk_ceiling="High")` — Literal["High", "Restricted"]
- [ ] `conftest.py`: `PlaintextCredential(credential_id="...", credential_kind="fernet", value="...")`
- [ ] `conftest.py`: `DummyTool`, `HighRiskDummyTool`, `RestrictedDummyTool` 3개 fixture
- [ ] `test_base_tool.py`: `__init_subclass__` TypeError 검증
- [ ] `test_runtime_validator.py`: field path `"input."` prefix 확인
- [ ] `test_risk_assessment_service.py`: RESTRICTED with High ceiling → AuthorizationError
- [ ] `test_execute_tool_use_case.py`: `finally` wipe 보장 — 성공/실패 모두 `credential.value == ""`
- [ ] `test_execute_tool_use_case.py`: 비도메인 예외 → `ToolExecutionError` 래핑
- [ ] `test_list_tools_use_case.py`: risk_level 필터 동작
- [ ] `test_tool_execution_service.py`: RuntimeError → ToolExecutionError 래핑
