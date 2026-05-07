from __future__ import annotations

from common_schemas.security import PlaintextCredential

from ..entities.base_tool import BaseTool
from ..exceptions import ToolExecutionError
from .runtime_validator import RuntimeValidator


class ToolExecutionService:
    """파이프라인: validate_input → tool.execute() → validate_output

    credential lifecycle(acquire/wipe/release)은 ExecuteToolUseCase에서 관리.
    """

    def __init__(self, validator: RuntimeValidator) -> None:
        self._validator = validator

    async def execute(
        self,
        tool: BaseTool,
        params: dict,
        credential: PlaintextCredential | None = None,
    ) -> dict:
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
