from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "bigquery_query"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


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
        category="데이터 소스",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = BigqueryQueryInput
    output_schema = BigqueryQueryOutput

    async def process(self, input: BigqueryQueryInput) -> BigqueryQueryOutput:
        raise NotImplementedError(
            "BigQuery 호출은 REQ-005 toolset connector를 통해 처리. "
            "GCP 자격증명(service account)은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="BigQuery 쿼리",
        category="데이터 소스",
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
                "schema": {"type": "array", "items": {"type": "object"}},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["google"],
        description="Google BigQuery Standard SQL 쿼리 실행. GCP service account 또는 OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
