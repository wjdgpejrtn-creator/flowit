from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse
from uuid import uuid5

import asyncpg
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ._url_guard import validate_outbound_host

_NODE_TYPE = "postgresql_query"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    """datetime·Decimal·UUID 등 비-JSON 타입을 str로 강제 — 결과 영속화/SSE 호환."""
    return json.loads(json.dumps(dict(row), default=str))


@dataclass
class PostgresqlQueryInput:
    query: str  # SQL 문 (`$1, $2, ...` 파라미터 placeholder 지원)
    parameters: list[Any] = field(default_factory=list)
    fetch_mode: str = "all"  # all | one | none — 결과 fetch 모드
    timeout_seconds: float = 30.0


@dataclass
class PostgresqlQueryOutput:
    rows: list[dict[str, Any]]  # fetch_mode=all/one일 때
    row_count: int  # 영향받은 행 수 (INSERT/UPDATE/DELETE)
    fields: list[str]  # 컬럼명 목록


class PostgresqlQueryNode(BaseNode[PostgresqlQueryInput, PostgresqlQueryOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="PostgreSQL 쿼리",
        category="integration",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = PostgresqlQueryInput
    output_schema = PostgresqlQueryOutput

    async def process(self, input: PostgresqlQueryInput, context: NodeContext) -> PostgresqlQueryOutput:
        # connection_token = PostgreSQL 연결 DSN (postgresql://user:pass@host:port/db).
        if not context.connection_token:
            raise ValidationError("postgresql_query는 credential(연결 DSN)이 필요하다")
        parsed = urlparse(context.connection_token)
        if parsed.hostname:  # SSRF — 내부 대역 DB 호스트 차단
            await validate_outbound_host(parsed.hostname, parsed.port or 5432)

        conn = await asyncpg.connect(context.connection_token, timeout=input.timeout_seconds)
        try:
            if input.fetch_mode == "none":
                status = await conn.execute(input.query, *input.parameters, timeout=input.timeout_seconds)
                # asyncpg execute는 "INSERT 0 3" / "UPDATE 2" 형태 상태 문자열을 반환.
                tail = status.split()
                row_count = int(tail[-1]) if tail and tail[-1].isdigit() else 0
                return PostgresqlQueryOutput(rows=[], row_count=row_count, fields=[])

            if input.fetch_mode == "one":
                record = await conn.fetchrow(input.query, *input.parameters, timeout=input.timeout_seconds)
                rows = [_jsonable(record)] if record is not None else []
            else:
                records = await conn.fetch(input.query, *input.parameters, timeout=input.timeout_seconds)
                rows = [_jsonable(r) for r in records]
            return PostgresqlQueryOutput(
                rows=rows,
                row_count=len(rows),
                fields=list(rows[0].keys()) if rows else [],
            )
        finally:
            await conn.close()


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="PostgreSQL 쿼리",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL 문 ($1, $2 ... placeholder 사용)"},
                "parameters": {
                    "type": "array",
                    "description": "쿼리의 $1, $2 자리에 바인딩할 값 목록(SQL 인젝션 방지)",
                },
                "fetch_mode": {
                    "type": "string",
                    "enum": ["all", "one", "none"],
                    "default": "all",
                    "description": "결과 반환 방식. all=전체 행, one=첫 행, none=결과 없음(INSERT 등). 기본값 all",
                },
                "timeout_seconds": {"type": "number", "default": 30.0, "description": "쿼리 제한 시간(초). 기본값 30"},
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
        required_connections=["postgresql"],
        description="PostgreSQL 데이터베이스에 SQL 쿼리 실행. asyncpg 기반 비동기 호출. DB 자격증명 필요",
        is_mvp=True,
        service_type="postgresql",
    )
