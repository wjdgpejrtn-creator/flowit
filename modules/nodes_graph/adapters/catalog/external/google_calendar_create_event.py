from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "google_calendar_create_event"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


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
        category="외부 API 연동",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = GoogleCalendarCreateEventInput
    output_schema = GoogleCalendarCreateEventOutput

    async def process(self, input: GoogleCalendarCreateEventInput) -> GoogleCalendarCreateEventOutput:
        raise NotImplementedError(
            "Calendar API 호출은 REQ-005 toolset connector를 통해 처리. "
            "Google OAuth 자격증명 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Google Calendar 이벤트 생성",
        category="외부 API 연동",
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
