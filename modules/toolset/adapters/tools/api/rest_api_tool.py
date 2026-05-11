from __future__ import annotations

import json
from typing import Any

import httpx

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError


class RestApiTool(BaseTool):
    name = "rest_api"
    description = "REST API 호출 및 JSON 응답 파싱"
    version = "1.0.0"
    risk_level = RiskLevel.MEDIUM

    input_schema = {
        "type": "object",
        "properties": {
            "base_url": {"type": "string"},
            "path": {"type": "string", "default": ""},
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "default": "GET",
            },
            "query_params": {"type": "object"},
            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "body": {"type": "object"},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
        },
        "required": ["base_url"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "status_code": {"type": "integer"},
            "data": {},
            "ok": {"type": "boolean"},
        },
        "required": ["status_code", "data", "ok"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        connector = kwargs.get("connector")
        credential = kwargs.get("credential")

        base_url = input_data["base_url"].rstrip("/")
        path = input_data.get("path", "").lstrip("/")
        url = f"{base_url}/{path}" if path else base_url
        method = input_data.get("method", "GET").upper()
        headers = {**{"Content-Type": "application/json", "Accept": "application/json"}, **(input_data.get("headers") or {})}
        body = input_data.get("body")
        params = input_data.get("query_params")
        timeout = input_data.get("timeout_seconds", 30)

        try:
            if connector is not None and credential is not None:
                response = await connector.connect(
                    endpoint=url,
                    credentials=credential,
                    method=method,
                    headers=headers,
                    body=body,
                    params=params,
                    timeout=timeout,
                )
                raw = response.body
                status_code = response.status_code
            else:
                content = json.dumps(body).encode() if body is not None else None
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.request(method=method, url=url, headers=headers, content=content, params=params)
                raw = resp.content
                status_code = resp.status_code

            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = raw.decode("utf-8", errors="replace")

            return {"status_code": status_code, "data": data, "ok": 200 <= status_code < 300}

        except ToolExecutionError:
            raise
        except httpx.TimeoutException as e:
            raise ToolExecutionError(message=f"REST API call to '{url}' timed out", code="TOOL_EXECUTION_ERROR") from e
        except httpx.RequestError as e:
            raise ToolExecutionError(message=f"REST API call to '{url}' failed: {e}", code="TOOL_EXECUTION_ERROR") from e
