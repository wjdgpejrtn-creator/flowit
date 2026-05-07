from __future__ import annotations

import jsonschema
import jsonschema.exceptions

from common_schemas.exceptions import ValidationError

from ..value_objects.tool_input import ToolInput
from ..value_objects.tool_output import ToolOutput


class RuntimeValidator:
    """jsonschema.Draft7Validator로 도구 I/O 검증. 복수 오류 중 첫 번째만 보고."""

    def validate_input(self, params: dict, schema: dict) -> ToolInput:
        self._validate(params, schema, prefix="input")
        return ToolInput(data=params)

    def validate_output(self, result: dict, schema: dict) -> ToolOutput:
        self._validate(result, schema, prefix="output")
        return ToolOutput(data=result)

    def _validate(self, data: dict, schema: dict, prefix: str) -> None:
        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(data))

        if errors:
            first = errors[0]
            path = ".".join(str(p) for p in first.absolute_path) or "root"
            raise ValidationError(
                message=f"[{prefix}.{path}] {first.message}",
                code="E_NODE_TYPE_MISMATCH",
            )
