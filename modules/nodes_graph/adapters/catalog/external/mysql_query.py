from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid5

import aiomysql
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ._url_guard import validate_outbound_host

_NODE_TYPE = "mysql_query"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    """datetime·Decimal 등 비-JSON 타입을 str로 강제 — 결과 영속화/SSE 호환."""
    return json.loads(json.dumps(dict(row), default=str))


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
        category="integration",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = MysqlQueryInput
    output_schema = MysqlQueryOutput

    async def process(self, input: MysqlQueryInput, context: NodeContext) -> MysqlQueryOutput:
        # connection_token = MySQL 연결 URL (mysql://user:pass@host:port/db).
        if not context.connection_token:
            raise ValidationError("mysql_query는 credential(연결 URL)이 필요하다")
        parsed = urlparse(context.connection_token)
        if not parsed.hostname:
            raise ValidationError("mysql 연결 URL 형식 오류 (mysql://user:pass@host:port/db)")
        await validate_outbound_host(parsed.hostname, parsed.port or 3306)  # SSRF

        conn = await aiomysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=unquote(parsed.username or ""),
            password=unquote(parsed.password or ""),
            db=parsed.path.lstrip("/") or None,
            connect_timeout=input.timeout_seconds,
        )
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(input.query, tuple(input.parameters) or None)
                if input.fetch_mode == "none":
                    await conn.commit()
                    return MysqlQueryOutput(rows=[], row_count=cursor.rowcount, fields=[])

                if input.fetch_mode == "one":
                    row = await cursor.fetchone()
                    rows = [_jsonable(row)] if row else []
                else:
                    rows = [_jsonable(r) for r in await cursor.fetchall()]
                fields = [d[0] for d in cursor.description] if cursor.description else []
                return MysqlQueryOutput(rows=rows, row_count=len(rows), fields=fields)
        finally:
            conn.close()


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="MySQL 쿼리",
        category="integration",
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
