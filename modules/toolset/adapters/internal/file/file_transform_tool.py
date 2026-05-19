from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.entities.tool_metadata import ToolCategory
from ....domain.exceptions import ToolExecutionError

_SUPPORTED = {"csv", "json"}


class FileTransformTool(BaseTool):
    name = "file_transform"
    description = "파일 포맷 변환 (CSV ↔ JSON)"
    version = "1.0.0"
    risk_level = RiskLevel.LOW
    category = ToolCategory.FILE
    capabilities = ["file_transform", "format_conversion"]

    input_schema = {
        "type": "object",
        "properties": {
            "source_path": {"type": "string"},
            "target_path": {"type": "string"},
            "source_format": {"type": "string", "enum": ["csv", "json"]},
            "target_format": {"type": "string", "enum": ["csv", "json"]},
            "encoding": {"type": "string", "default": "utf-8"},
        },
        "required": ["source_path", "target_path", "source_format", "target_format"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "target_path": {"type": "string"},
            "rows_processed": {"type": "integer"},
        },
        "required": ["target_path", "rows_processed"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        src = Path(input_data["source_path"])
        dst = Path(input_data["target_path"])
        src_fmt = input_data["source_format"]
        dst_fmt = input_data["target_format"]
        encoding = input_data.get("encoding", "utf-8")

        if not src.exists():
            raise ToolExecutionError(message=f"Source file not found: {src}", code="TOOL_EXECUTION_ERROR")

        try:
            raw = src.read_text(encoding=encoding)

            if src_fmt == "csv":
                reader = csv.DictReader(StringIO(raw))
                rows = list(reader)
            elif src_fmt == "json":
                loaded = json.loads(raw)
                rows = loaded if isinstance(loaded, list) else [loaded]
            else:
                raise ToolExecutionError(message=f"Unsupported source format: {src_fmt}", code="TOOL_EXECUTION_ERROR")

            if dst_fmt == "json":
                dst.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding=encoding)
            elif dst_fmt == "csv":
                if not rows:
                    dst.write_text("", encoding=encoding)
                else:
                    buf = StringIO()
                    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
                    dst.write_text(buf.getvalue(), encoding=encoding)
            else:
                raise ToolExecutionError(message=f"Unsupported target format: {dst_fmt}", code="TOOL_EXECUTION_ERROR")

            return {"target_path": str(dst), "rows_processed": len(rows)}

        except ToolExecutionError:
            raise
        except (OSError, json.JSONDecodeError, csv.Error) as e:
            raise ToolExecutionError(message=f"File transform failed: {e}", code="TOOL_EXECUTION_ERROR") from e
