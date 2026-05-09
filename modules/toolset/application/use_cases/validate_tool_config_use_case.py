from __future__ import annotations

from ...domain.ports.tool_registry import ToolRegistry
from ...domain.services.runtime_validator import RuntimeValidator


class ValidateToolConfigUseCase:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        validator: RuntimeValidator,
    ) -> None:
        self._registry = tool_registry
        self._validator = validator

    def execute(self, tool_name: str, parameters: dict) -> bool:
        tool = self._registry.get(tool_name)
        self._validator.validate_input(parameters, tool.input_schema)
        return True
