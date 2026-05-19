from __future__ import annotations

from pathlib import Path
from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.entities.tool_metadata import ToolCategory
from ....domain.exceptions import ToolExecutionError


class FileReadTool(BaseTool):
    name = "file_read"
    description = "파일 읽기 (텍스트/바이너리)"
    version = "1.0.0"
    risk_level = RiskLevel.LOW
    category = ToolCategory.FILE
    capabilities = ["file_read", "file_access"]

    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "encoding": {"type": "string", "default": "utf-8"},
            "binary": {"type": "boolean", "default": False},
        },
        "required": ["path"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "content": {},
            "size_bytes": {"type": "integer"},
            "path": {"type": "string"},
        },
        "required": ["content", "size_bytes", "path"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        file_path = Path(input_data["path"])
        encoding = input_data.get("encoding", "utf-8")
        binary = input_data.get("binary", False)

        if not file_path.exists():
            raise ToolExecutionError(
                message=f"File not found: {file_path}",
                code="TOOL_EXECUTION_ERROR",
            )
        if not file_path.is_file():
            raise ToolExecutionError(
                message=f"Path is not a file: {file_path}",
                code="TOOL_EXECUTION_ERROR",
            )

        try:
            if binary:
                content: Any = file_path.read_bytes().hex()
            else:
                content = file_path.read_text(encoding=encoding)
            return {"content": content, "size_bytes": file_path.stat().st_size, "path": str(file_path)}
        except OSError as e:
            raise ToolExecutionError(message=f"Failed to read file '{file_path}': {e}", code="TOOL_EXECUTION_ERROR") from e
