from __future__ import annotations

from typing import Any

import httpx

from common_schemas.enums import RiskLevel

from ....domain.base_tool import BaseTool
from ....domain.exceptions import ToolExecutionError


class SlackNotifyTool(BaseTool):
    name = "slack_notify"
    description = "Slack 메시지 전송 (Webhook URL 기반, 비가역적)"
    version = "1.0.0"
    risk_level = RiskLevel.HIGH

    input_schema = {
        "type": "object",
        "properties": {
            "webhook_url": {"type": "string"},
            "message": {"type": "string"},
            "channel": {"type": "string"},
            "username": {"type": "string"},
            "icon_emoji": {"type": "string"},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
        },
        "required": ["webhook_url", "message"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "sent": {"type": "boolean"},
            "status_code": {"type": "integer"},
        },
        "required": ["sent", "status_code"],
    }

    async def execute(self, input_data: dict[str, Any], **kwargs) -> dict[str, Any]:
        webhook_url = input_data["webhook_url"]
        timeout = input_data.get("timeout_seconds", 10)

        payload: dict[str, Any] = {"text": input_data["message"]}
        for key in ("channel", "username", "icon_emoji"):
            if input_data.get(key):
                payload[key] = input_data[key]

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(webhook_url, json=payload)
            return {"sent": resp.status_code == 200, "status_code": resp.status_code}

        except httpx.TimeoutException as e:
            raise ToolExecutionError(message=f"Slack notification timed out: {e}", code="TOOL_EXECUTION_ERROR") from e
        except httpx.RequestError as e:
            raise ToolExecutionError(message=f"Slack notification failed: {e}", code="TOOL_EXECUTION_ERROR") from e
