from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from .._catalog_ns import _CATALOG_NS

_NODE_TYPE = "date_format"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class DateFormatInput:
    date_str: str
    input_format: str = "%Y-%m-%d %H:%M:%S"
    output_format: str = "%Y-%m-%d %H:%M:%S"
    add_days: int = 0
    add_hours: int = 0
    add_minutes: int = 0


@dataclass
class DateFormatOutput:
    result: str
    iso: str
    timestamp: float


class DateFormatNode(BaseNode[DateFormatInput, DateFormatOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="날짜 포맷 변환",
        category="transform",
        risk_level=RiskLevel.LOW,
        is_mvp=True,
    )
    input_schema = DateFormatInput
    output_schema = DateFormatOutput

    async def process(self, input: DateFormatInput) -> DateFormatOutput:
        dt = datetime.strptime(input.date_str, input.input_format)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        dt += timedelta(days=input.add_days, hours=input.add_hours, minutes=input.add_minutes)
        return DateFormatOutput(
            result=dt.strftime(input.output_format),
            iso=dt.isoformat(),
            timestamp=dt.timestamp(),
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="날짜 포맷 변환",
        category="transform",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "date_str": {"type": "string"},
                "input_format": {"type": "string", "default": "%Y-%m-%d %H:%M:%S"},
                "output_format": {"type": "string", "default": "%Y-%m-%d %H:%M:%S"},
                "add_days": {"type": "integer", "default": 0},
                "add_hours": {"type": "integer", "default": 0},
                "add_minutes": {"type": "integer", "default": 0},
            },
            "required": ["date_str"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "string"},
                "iso": {"type": "string"},
                "timestamp": {"type": "number"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.LOW,
        required_connections=[],
        description="날짜 파싱/포맷 변환 및 날짜 연산 (일/시/분 가감)",
        is_mvp=True,
        service_type=None,
    )
