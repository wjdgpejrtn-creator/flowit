from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError, ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "bigquery_query"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_TIMEOUT_SECONDS = 120  # BigQuery 쿼리 — 넉넉히


@dataclass
class BigqueryQueryInput:
    project_id: str
    query: str                                                  # Standard SQL
    parameters: list[dict[str, Any]] = field(default_factory=list)  # [{"name": ..., "value": ..., "type": ...}]
    location: str = "US"                                        # asia-northeast3 등
    dry_run: bool = False                                       # True이면 비용 추정만, 실행 안 함
    use_legacy_sql: bool = False
    maximum_bytes_billed: int | None = None                     # 비용 상한 (바이트)


@dataclass
class BigqueryQueryOutput:
    job_id: str
    rows: list[dict[str, Any]]
    total_rows: int
    total_bytes_processed: int
    schema: list[dict[str, str]]                                # [{"name": ..., "type": ...}, ...]


class BigqueryQueryNode(BaseNode[BigqueryQueryInput, BigqueryQueryOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="BigQuery 쿼리",
        category="integration",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = BigqueryQueryInput
    output_schema = BigqueryQueryOutput

    async def process(self, input: BigqueryQueryInput, context: NodeContext) -> BigqueryQueryOutput:
        # connection_token = Google OAuth access token. BigQuery REST jobs.query 호출
        # (google-cloud-bigquery SDK 의존 회피 — 다른 Google 노드와 동일 httpx 패턴).
        if not context.connection_token:
            raise ValidationError("bigquery_query는 credential(Google OAuth 토큰)이 필요하다")

        body: dict[str, Any] = {
            "query": input.query,
            "useLegacySql": input.use_legacy_sql,
            "location": input.location,
            "dryRun": input.dry_run,
        }
        if input.maximum_bytes_billed is not None:
            body["maximumBytesBilled"] = str(input.maximum_bytes_billed)
        if input.parameters:
            body["parameterMode"] = "NAMED"
            body["queryParameters"] = [
                {
                    "name": p["name"],
                    "parameterType": {"type": p.get("type", "STRING")},
                    "parameterValue": {"value": p["value"]},
                }
                for p in input.parameters
            ]

        url = f"https://bigquery.googleapis.com/bigquery/v2/projects/{input.project_id}/queries"
        headers = {
            "Authorization": f"Bearer {context.connection_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=body, headers=headers)

        if response.status_code >= 400:
            raise ExecutionError(
                f"BigQuery API 오류 {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        schema_fields = data.get("schema", {}).get("fields", [])
        field_names = [f["name"] for f in schema_fields]
        # BigQuery 응답 row 포맷: {"f": [{"v": 값}, ...]} → schema 이름과 zip.
        rows: list[dict[str, Any]] = []
        for record in data.get("rows", []):
            cells = record.get("f", [])
            rows.append(
                {field_names[i]: cells[i].get("v") for i in range(min(len(field_names), len(cells)))}
            )
        return BigqueryQueryOutput(
            job_id=data.get("jobReference", {}).get("jobId", ""),
            rows=rows,
            total_rows=int(data.get("totalRows", 0) or 0),
            total_bytes_processed=int(data.get("totalBytesProcessed", 0) or 0),
            schema=[{"name": f["name"], "type": f["type"]} for f in schema_fields],
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="BigQuery 쿼리",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string"},
                "query": {"type": "string", "description": "Standard SQL"},
                "parameters": {"type": "array", "items": {"type": "object"}},
                "location": {"type": "string", "default": "US"},
                "dry_run": {"type": "boolean", "default": False},
                "use_legacy_sql": {"type": "boolean", "default": False},
                "maximum_bytes_billed": {"type": ["integer", "null"]},
            },
            "required": ["project_id", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "rows": {"type": "array", "items": {"type": "object"}},
                "total_rows": {"type": "integer"},
                "total_bytes_processed": {"type": "integer"},
                "schema": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string"},
                        },
                    },
                },
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["google"],
        description="Google BigQuery Standard SQL 쿼리 실행. GCP service account 또는 OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
