from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "mysql_query"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class MysqlQueryInput:
    query: str                                                  # SQL 문 (`%s` 파라미터 placeholder)
    parameters: list[Any] = field(default_factory=list)
    fetch_mode: str = "all"                                     # all | one | none
    timeout_seconds: float = 30.0


@dataclass
class MysqlQueryOutput:
    rows: list[dict[str, Any]]
    row_count: int
    fields: list[str]


class MysqlQueryNode(BaseNode[MysqlQueryInput, MysqlQueryOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="MySQL 쿼리",
        category="데이터 소스",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = MysqlQueryInput
    output_schema = MysqlQueryOutput

    async def process(self, input: MysqlQueryInput) -> MysqlQueryOutput:
        raise NotImplementedError(
            "DB 연결은 REQ-005 toolset connector를 통해 처리. "
            "연결 정보(host/port/user/password)는 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="MySQL 쿼리",
        category="데이터 소스",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL 문 (%s placeholder 사용)"},
                "parameters": {"type": "array"},
                "fetch_mode": {"type": "string", "enum": ["all", "one", "none"], "default": "all"},
                "timeout_seconds": {"type": "number", "default": 30.0},
            },
            "required": ["query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "rows": {"type": "array", "items": {"type": "object"}},
                "row_count": {"type": "integer"},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["mysql"],
        description="MySQL 데이터베이스에 SQL 쿼리 실행. aiomysql 기반 비동기 호출. DB 자격증명 필요",
        is_mvp=True,
        service_type="mysql",
    )
