from __future__ import annotations

import pytest
from unittest.mock import AsyncMock
from uuid import uuid4

from common_schemas.exceptions import AuthorizationError, ValidationError
from common_schemas.security import PermissionSource, PlaintextCredential

from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter
from toolset.application.use_cases.execute_tool_use_case import ExecuteToolUseCase
from toolset.domain.exceptions import CredentialError, ToolExecutionError
from toolset.domain.services.risk_assessment_service import RiskAssessmentService
from toolset.domain.services.runtime_validator import RuntimeValidator
from toolset.domain.services.tool_execution_service import ToolExecutionService
from toolset.domain.value_objects import ToolOutput
from toolset.tests.fixtures import DummyTool, RestrictedDummyTool


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
    execution_svc=None,
    execution_repo=None,
    credential_injection_svc=None,
):
    if tool_registry is None:
        reg = ToolRegistryAdapter()
        reg.register_tool(DummyTool(), tool_id=uuid4())
        tool_registry = reg

    return ExecuteToolUseCase(
        tool_registry=tool_registry,
        secure_connector=secure_connector or AsyncMock(),
        execution_svc=execution_svc or ToolExecutionService(validator=RuntimeValidator()),
        risk_service=RiskAssessmentService(),
        execution_repo=execution_repo or AsyncMock(),
        credential_injection_svc=credential_injection_svc or AsyncMock(),
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
        assert isinstance(result, ToolOutput)
        assert result.data == {"result": "ok: hello"}

    @pytest.mark.asyncio
    async def test_execute_with_credential(self, mock_credential):
        cred_svc = AsyncMock()
        cred_svc.inject.return_value = mock_credential

        uc = make_use_case(credential_injection_svc=cred_svc)
        cred_id = uuid4()
        node_id = uuid4()

        result = await uc.execute(
            tool_name="dummy",
            input_data={"message": "world"},
            context=make_permission("High"),
            credential_id=cred_id,
            node_id=node_id,
        )
        assert result.data["result"] == "ok: world"
        cred_svc.inject.assert_called_once_with(cred_id, node_id)


class TestCredentialLifecycle:
    @pytest.mark.asyncio
    async def test_credential_wiped_on_success(self, mock_credential):
        cred_svc = AsyncMock()
        cred_svc.inject.return_value = mock_credential

        uc = make_use_case(credential_injection_svc=cred_svc)
        await uc.execute(
            "dummy", {"message": "x"}, make_permission("High"),
            credential_id=uuid4(), node_id=uuid4(),
        )
        assert mock_credential.value == ""

    @pytest.mark.asyncio
    async def test_credential_wiped_on_tool_error(self, mock_credential):
        class FailingTool(DummyTool):
            name = "failing"
            async def execute(self, input_data, **kwargs):
                raise ValueError("External API down")

        reg = ToolRegistryAdapter()
        reg.register_tool(FailingTool(), tool_id=uuid4())

        cred_svc = AsyncMock()
        cred_svc.inject.return_value = mock_credential
        uc = make_use_case(tool_registry=reg, credential_injection_svc=cred_svc)

        with pytest.raises(ToolExecutionError):
            await uc.execute(
                "failing", {"message": "x"}, make_permission("High"),
                credential_id=uuid4(), node_id=uuid4(),
            )
        assert mock_credential.value == ""

    @pytest.mark.asyncio
    async def test_credential_not_injected_when_credential_id_none(self):
        cred_svc = AsyncMock()
        uc = make_use_case(credential_injection_svc=cred_svc)

        await uc.execute("dummy", {"message": "x"}, make_permission("High"), credential_id=None)
        cred_svc.inject.assert_not_called()

    @pytest.mark.asyncio
    async def test_credential_id_without_node_id_raises_credential_error(self):
        uc = make_use_case()
        with pytest.raises(CredentialError) as exc_info:
            await uc.execute(
                "dummy", {"message": "x"}, make_permission("High"),
                credential_id=uuid4(), node_id=None,
            )
        assert exc_info.value.code == "E_CREDENTIAL_NODE_ID_MISSING"


class TestPermissionGating:
    @pytest.mark.asyncio
    async def test_restricted_tool_with_high_ceiling_raises_authorization_error(self):
        reg = ToolRegistryAdapter()
        reg.register_tool(RestrictedDummyTool(), tool_id=uuid4())
        uc = make_use_case(tool_registry=reg)

        with pytest.raises(AuthorizationError):
            await uc.execute("restricted_dummy", {}, make_permission("High"))


class TestValidationError:
    @pytest.mark.asyncio
    async def test_invalid_input_raises_validation_error(self):
        uc = make_use_case()
        with pytest.raises(ValidationError):
            await uc.execute("dummy", {"wrong_field": 123}, make_permission("High"))


class TestNonDomainExceptionWrapping:
    @pytest.mark.asyncio
    async def test_unexpected_exception_wrapped_as_tool_execution_error(self):
        class CrashTool(DummyTool):
            name = "crash"
            async def execute(self, input_data, **kwargs):
                raise RuntimeError("unexpected crash")

        reg = ToolRegistryAdapter()
        reg.register_tool(CrashTool(), tool_id=uuid4())
        uc = make_use_case(tool_registry=reg)

        with pytest.raises(ToolExecutionError) as exc_info:
            await uc.execute("crash", {"message": "x"}, make_permission("High"))
        assert "unexpected crash" in str(exc_info.value)


class TestRepoBestEffort:
    @pytest.mark.asyncio
    async def test_repo_save_failure_does_not_propagate(self):
        repo = AsyncMock()
        repo.save.side_effect = Exception("DB down")
        uc = make_use_case(execution_repo=repo)

        result = await uc.execute("dummy", {"message": "hi"}, make_permission("High"))
        assert isinstance(result, ToolOutput)
        assert result.data == {"result": "ok: hi"}
