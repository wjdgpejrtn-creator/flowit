from __future__ import annotations

from dataclasses import dataclass, field
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

_NODE_TYPE = "google_calendar_create_event"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_TIMEOUT_SECONDS = 60


@dataclass
class GoogleCalendarCreateEventInput:
    calendar_id: str                                            # "primary" 또는 캘린더 ID
    summary: str                                                # 이벤트 제목
    start: str                                                  # ISO 8601 (e.g. "2026-05-11T09:00:00+09:00")
    end: str                                                    # ISO 8601
    description: str | None = None
    location: str | None = None
    attendees: list[str] = field(default_factory=list)          # 이메일 목록
    timezone: str = "Asia/Seoul"
    send_updates: str = "none"                                  # all | externalOnly | none
    reminders: list[dict[str, Any]] = field(default_factory=list)  # [{"method": "email"|"popup", "minutes": ...}]


@dataclass
class GoogleCalendarCreateEventOutput:
    event_id: str
    html_link: str                                              # 캘린더 웹 링크
    ical_uid: str
    status: str                                                 # confirmed | tentative | cancelled
    created: str                                                # ISO 8601


class GoogleCalendarCreateEventNode(BaseNode[GoogleCalendarCreateEventInput, GoogleCalendarCreateEventOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Google Calendar 이벤트 생성",
        category="integration",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = GoogleCalendarCreateEventInput
    output_schema = GoogleCalendarCreateEventOutput

    async def process(
        self, input: GoogleCalendarCreateEventInput, context: NodeContext
    ) -> GoogleCalendarCreateEventOutput:
        # connection_token = Google OAuth access token. Calendar events.insert.
        if not context.connection_token:
            raise ValidationError("google_calendar_create_event는 credential(Google OAuth 토큰)이 필요하다")

        body: dict[str, Any] = {
            "summary": input.summary,
            "start": {"dateTime": input.start, "timeZone": input.timezone},
            "end": {"dateTime": input.end, "timeZone": input.timezone},
        }
        if input.description:
            body["description"] = input.description
        if input.location:
            body["location"] = input.location
        if input.attendees:
            body["attendees"] = [{"email": email} for email in input.attendees]
        if input.reminders:
            body["reminders"] = {"useDefault": False, "overrides": input.reminders}

        url = (
            f"https://www.googleapis.com/calendar/v3/calendars/"
            f"{quote(input.calendar_id, safe='')}/events"
        )
        headers = {
            "Authorization": f"Bearer {context.connection_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url, params={"sendUpdates": input.send_updates}, json=body, headers=headers
            )

        if response.status_code >= 400:
            raise ExecutionError(
                f"Google Calendar API 오류 {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        return GoogleCalendarCreateEventOutput(
            event_id=data.get("id", ""),
            html_link=data.get("htmlLink", ""),
            ical_uid=data.get("iCalUID", ""),
            status=data.get("status", ""),
            created=data.get("created", ""),
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Google Calendar 이벤트 생성",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "calendar_id": {"type": "string", "default": "primary"},
                "summary": {"type": "string"},
                "start": {"type": "string", "format": "date-time"},
                "end": {"type": "string", "format": "date-time"},
                "description": {"type": ["string", "null"]},
                "location": {"type": ["string", "null"]},
                "attendees": {"type": "array", "items": {"type": "string", "format": "email"}},
                "timezone": {"type": "string", "default": "Asia/Seoul"},
                "send_updates": {"type": "string", "enum": ["all", "externalOnly", "none"], "default": "none"},
                "reminders": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["calendar_id", "summary", "start", "end"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "html_link": {"type": "string"},
                "ical_uid": {"type": "string"},
                "status": {"type": "string"},
                "created": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["google"],
        description="Google Calendar에 이벤트 생성 (events.insert). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
