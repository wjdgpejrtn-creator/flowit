import pytest
from common_schemas.exceptions import ValidationError

from toolset.domain.services import RuntimeValidator
from toolset.domain.value_objects import ToolInput, ToolOutput


class TestRuntimeValidator:

    def setup_method(self):
        self.validator = RuntimeValidator()

    def test_validate_input_returns_tool_input(self):
        schema = {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        }
        result = self.validator.validate_input({"message": "hello"}, schema)
        assert isinstance(result, ToolInput)
        assert result.data == {"message": "hello"}

    def test_validate_input_invalid_raises_validation_error(self):
        schema = {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        }
        with pytest.raises(ValidationError):
            self.validator.validate_input({}, schema)

    def test_validate_output_returns_tool_output(self):
        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        }
        result = self.validator.validate_output({"result": "ok"}, schema)
        assert isinstance(result, ToolOutput)
        assert result.data == {"result": "ok"}

    def test_validate_output_invalid_raises_validation_error(self):
        schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        }
        with pytest.raises(ValidationError):
            self.validator.validate_output({"wrong_key": "value"}, schema)
