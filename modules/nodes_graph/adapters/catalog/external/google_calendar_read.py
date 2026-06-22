from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError, ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "google_calendar_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_TIMEOUT_SECONDS = 60


@dataclass
class GoogleCalendarReadInput:
    calendar_id: str = "primary"                                # "primary" 또는 캘린더 ID
    time_min: str | None = None                                 # ISO 8601 하한 (이 시각 이후 이벤트)
    time_max: str | None = None                                 # ISO 8601 상한
    query: str | None = None                                    # 자유 텍스트 검색
    max_results: int = 10


@dataclass
class GoogleCalendarReadOutput:
    events: list[dict[str, Any]]                                # [{id, summary, start, end, status, html_link}]
    count: int


class GoogleCalendarReadNode(BaseNode[GoogleCalendarReadInput, GoogleCalendarReadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Google Calendar 이벤트 조회",
        category="integration",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = GoogleCalendarReadInput
    output_schema = GoogleCalendarReadOutput

    async def process(self, input: GoogleCalendarReadInput, context: NodeContext) -> GoogleCalendarReadOutput:
        # connection_token = Google OAuth access token. Calendar events.list (singleEvents 전개).
        if not context.connection_token:
            raise ValidationError("google_calendar_read는 credential(Google OAuth 토큰)이 필요하다")

        url = (
            f"https://www.googleapis.com/calendar/v3/calendars/"
            f"{quote(input.calendar_id, safe='')}/events"
        )
        params: dict[str, Any] = {
            "maxResults": input.max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        if input.time_min:
            params["timeMin"] = input.time_min
        if input.time_max:
            params["timeMax"] = input.time_max
        if input.query:
            params["q"] = input.query
        headers = {"Authorization": f"Bearer {context.connection_token}"}

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(url, params=params, headers=headers)

        if response.status_code >= 400:
            raise ExecutionError(
                f"Google Calendar API 오류 {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        events = [
            {
                "id": item.get("id", ""),
                "summary": item.get("summary", ""),
                "start": item.get("start", {}),
                "end": item.get("end", {}),
                "status": item.get("status", ""),
                "html_link": item.get("htmlLink", ""),
            }
            for item in data.get("items", [])
        ]
        return GoogleCalendarReadOutput(events=events, count=len(events))


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Google Calendar 이벤트 조회",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "calendar_id": {"type": "string", "default": "primary"},
                "time_min": {"type": ["string", "null"], "format": "date-time"},
                "time_max": {"type": ["string", "null"], "format": "date-time"},
                "query": {"type": ["string", "null"]},
                "max_results": {"type": "integer", "default": 10},
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "summary": {"type": "string"},
                            "start": {"type": "object"},
                            "end": {"type": "object"},
                            "status": {"type": "string"},
                            "html_link": {"type": "string"},
                        },
                    },
                },
                "count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["google"],
        description="Google Calendar 이벤트 목록 조회 (events.list). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
