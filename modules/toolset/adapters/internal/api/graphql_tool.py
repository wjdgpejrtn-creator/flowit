from __future__ import annotations

import json
from typing import Any

import httpx

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.entities.tool_metadata import ToolCategory
from ....domain.exceptions import ToolExecutionError


class GraphqlTool(BaseTool):
    name = "graphql"
    description = "GraphQL 쿼리/뮤테이션 실행"
    version = "1.0.0"
    risk_level = RiskLevel.MEDIUM
    category = ToolCategory.API
    capabilities = ["graphql", "http_request", "external_integration"]

    input_schema = {
        "type": "object",
        "properties": {
            "endpoint": {"type": "string"},
            "query": {"type": "string"},
            "variables": {"type": "object"},
            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300, "default": 30},
        },
        "required": ["endpoint", "query"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "data": {},
            "errors": {"type": "array"},
            "ok": {"type": "boolean"},
        },
        "required": ["data", "ok"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        connector = kwargs.get("connector")
        credential = kwargs.get("credential")

        endpoint = input_data["endpoint"]
        payload = {"query": input_data["query"]}
        if input_data.get("variables"):
            payload["variables"] = input_data["variables"]
        headers = {**{"Content-Type": "application/json", "Accept": "application/json"}, **(input_data.get("headers") or {})}
        timeout = input_data.get("timeout_seconds", 30)

        try:
            if connector is not None and credential is not None:
                response = await connector.connect(
                    endpoint=endpoint,
                    credentials=credential,
                    method="POST",
                    headers=headers,
                    body=payload,
                    timeout=timeout,
                )
                raw = response.body
                status_code = response.status_code
            else:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(endpoint, json=payload, headers=headers)
                raw = resp.content
                status_code = resp.status_code

            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ToolExecutionError(message=f"GraphQL response is not valid JSON: {e}", code="TOOL_EXECUTION_ERROR") from e

            return {
                "data": result.get("data"),
                "errors": result.get("errors"),
                "ok": status_code < 300 and not result.get("errors"),
            }

        except ToolExecutionError:
            raise
        except httpx.TimeoutException as e:
            raise ToolExecutionError(message=f"GraphQL request to '{endpoint}' timed out", code="TOOL_EXECUTION_ERROR") from e
        except httpx.RequestError as e:
            raise ToolExecutionError(message=f"GraphQL request to '{endpoint}' failed: {e}", code="TOOL_EXECUTION_ERROR") from e
