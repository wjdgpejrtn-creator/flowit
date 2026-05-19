from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import httpx

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.entities.tool_metadata import ToolCategory
from ....domain.exceptions import ToolExecutionError


class WebhookTool(BaseTool):
    name = "webhook"
    description = "웹훅 발송 (fire-and-forget, 외부 엔드포인트 비가역적)"
    version = "1.0.0"
    risk_level = RiskLevel.HIGH
    category = ToolCategory.API
    capabilities = ["webhook", "event_trigger", "external_integration"]

    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "payload": {"type": "object"},
            "headers": {"type": "object", "additionalProperties": {"type": "string"}},
            "secret": {"type": "string"},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 60, "default": 10},
        },
        "required": ["url", "payload"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "status_code": {"type": "integer"},
            "delivered": {"type": "boolean"},
        },
        "required": ["status_code", "delivered"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        url = input_data["url"]
        payload = input_data["payload"]
        headers: dict[str, str] = {"Content-Type": "application/json", **(input_data.get("headers") or {})}
        secret = input_data.get("secret")
        timeout = input_data.get("timeout_seconds", 10)

        body_bytes = json.dumps(payload).encode()

        if secret:
            sig = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={sig}"

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, content=body_bytes, headers=headers)
            return {"status_code": resp.status_code, "delivered": resp.status_code < 300}

        except httpx.TimeoutException as e:
            raise ToolExecutionError(message=f"Webhook delivery to '{url}' timed out", code="TOOL_EXECUTION_ERROR") from e
        except httpx.RequestError as e:
            raise ToolExecutionError(message=f"Webhook delivery to '{url}' failed: {e}", code="TOOL_EXECUTION_ERROR") from e
