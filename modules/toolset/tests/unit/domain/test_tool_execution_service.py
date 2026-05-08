import pytest
from unittest.mock import AsyncMock

from toolset.domain.services import ToolExecutionService, RuntimeValidator
from toolset.domain.value_objects import ToolOutput
from toolset.domain.exceptions import ToolExecutionError
from toolset.tests.fixtures import DummyTool


class TestToolExecutionService:

    def setup_method(self):
        self.validator = RuntimeValidator()
        self.service = ToolExecutionService(validator=self.validator)

    @pytest.mark.asyncio
    async def test_execute_returns_tool_output(self, dummy_tool):
        result = await self.service.execute(dummy_tool, {"message": "hello"})
        assert isinstance(result, ToolOutput)
        assert result.data == {"result": "ok: hello"}

    @pytest.mark.asyncio
    async def test_invalid_input_raises_validation_error(self, dummy_tool):
        from common_schemas.exceptions import ValidationError
        with pytest.raises(ValidationError):
            await self.service.execute(dummy_tool, {})  # message 누락

    @pytest.mark.asyncio
    async def test_tool_exception_wrapped_as_tool_execution_error(self):
        class FailingTool(DummyTool):
            name = "failing"
            async def execute(self, input_data, **kwargs):
                raise RuntimeError("external api down")

        with pytest.raises(ToolExecutionError):
            await self.service.execute(FailingTool(), {"message": "x"})
