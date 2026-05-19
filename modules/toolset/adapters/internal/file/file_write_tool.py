from __future__ import annotations

from pathlib import Path
from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.entities.tool_metadata import ToolCategory
from ....domain.exceptions import ToolExecutionError


class FileWriteTool(BaseTool):
    name = "file_write"
    description = "파일 쓰기/생성 (로컬 쓰기)"
    version = "1.0.0"
    risk_level = RiskLevel.MEDIUM
    category = ToolCategory.FILE
    capabilities = ["file_write", "file_access"]

    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
            "encoding": {"type": "string", "default": "utf-8"},
            "mode": {"type": "string", "enum": ["w", "a"], "default": "w"},
            "create_parents": {"type": "boolean", "default": False},
        },
        "required": ["path", "content"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "bytes_written": {"type": "integer"},
            "success": {"type": "boolean"},
        },
        "required": ["path", "bytes_written", "success"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        file_path = Path(input_data["path"])
        content = input_data["content"]
        encoding = input_data.get("encoding", "utf-8")
        mode = input_data.get("mode", "w")
        create_parents = input_data.get("create_parents", False)

        if file_path.is_dir():
            raise ToolExecutionError(
                message=f"Path is a directory: {file_path}",
                code="TOOL_EXECUTION_ERROR",
            )

        try:
            if create_parents:
                file_path.parent.mkdir(parents=True, exist_ok=True)

            with file_path.open(mode=mode, encoding=encoding) as f:
                f.write(content)

            return {
                "path": str(file_path),
                "bytes_written": len(content.encode(encoding)),
                "success": True,
            }
        except OSError as e:
            raise ToolExecutionError(message=f"Failed to write file '{file_path}': {e}", code="TOOL_EXECUTION_ERROR") from e
