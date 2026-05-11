from __future__ import annotations

import json
from typing import Any

import httpx

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError


class HttpRequestTool(BaseTool):
    name = "http_request"
    description = "범용 HTTP 요청 (임의 URL, 모든 메서드, 비가역적)"
    version = "1.0.0"
    risk_level = RiskLevel.HIGH

    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
                "default": "GET",
            },
            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "body": {},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
        },
        "required": ["url"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "status_code": {"type": "integer"},
            "body": {},
            "headers": {"type": "object"},
        },
        "required": ["status_code", "body", "headers"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        connector = kwargs.get("connector")
        credential = kwargs.get("credential")

        url = input_data["url"]
        method = input_data.get("method", "GET").upper()
        headers = input_data.get("headers") or {}
        body = input_data.get("body")
        timeout = input_data.get("timeout_seconds", 30)

        try:
            if connector is not None and credential is not None:
                response = await connector.connect(
                    endpoint=url,
                    credentials=credential,
                    method=method,
                    headers=headers,
                    body=body,
                    timeout=timeout,
                )
                raw = response.body
                status_code = response.status_code
                resp_headers = response.headers
            else:
                content = json.dumps(body).encode() if body is not None else None
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.request(method=method, url=url, headers=headers, content=content)
                raw = resp.content
                status_code = resp.status_code
                resp_headers = dict(resp.headers)

            try:
                parsed_body = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                parsed_body = raw.decode("utf-8", errors="replace")

            return {"status_code": status_code, "body": parsed_body, "headers": resp_headers}

        except ToolExecutionError:
            raise
        except httpx.TimeoutException as e:
            raise ToolExecutionError(message=f"HTTP request to '{url}' timed out", code="TOOL_EXECUTION_ERROR") from e
        except httpx.RequestError as e:
            raise ToolExecutionError(message=f"HTTP request to '{url}' failed: {e}", code="TOOL_EXECUTION_ERROR") from e
