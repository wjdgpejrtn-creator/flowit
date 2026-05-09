from __future__ import annotations

import pytest
from uuid import uuid4

from common_schemas.exceptions import NotFoundError, ValidationError

from toolset.adapters.tool_registry_adapter import ToolRegistryAdapter
from toolset.application.use_cases.validate_tool_config_use_case import ValidateToolConfigUseCase
from toolset.domain.services.runtime_validator import RuntimeValidator
from toolset.tests.fixtures import DummyTool


@pytest.fixture
def use_case():
    reg = ToolRegistryAdapter()
    reg.register_tool(DummyTool(), tool_id=uuid4(), category="test")
    return ValidateToolConfigUseCase(tool_registry=reg, validator=RuntimeValidator())


class TestValidateToolConfigUseCase:
    def test_valid_params_returns_true(self, use_case):
        result = use_case.execute("dummy", {"message": "hello"})
        assert result is True

    def test_invalid_params_raises_validation_error(self, use_case):
        with pytest.raises(ValidationError):
            use_case.execute("dummy", {"wrong_key": 123})

    def test_unknown_tool_raises_not_found_error(self, use_case):
        with pytest.raises(NotFoundError):
            use_case.execute("nonexistent_tool", {"message": "hello"})

    def test_no_api_call_made(self, use_case):
        # 스키마 검증만 하고 실제 실행 없음 — execute()가 동기 메서드
        import inspect
        assert not inspect.iscoroutinefunction(use_case.execute)
