from __future__ import annotations

from dataclasses import dataclass
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

_NODE_TYPE = "linear_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_LINEAR_API_URL = "https://api.linear.app/graphql"
_TIMEOUT_SECONDS = 30
_ISSUES_QUERY = """
query Issues($filter: IssueFilter, $first: Int!) {
  issues(filter: $filter, first: $first) {
    nodes { id identifier title url priority state { name } assignee { name } createdAt }
  }
}
""".strip()


@dataclass
class LinearReadInput:
    team_id: str | None = None                                  # 팀 필터
    assignee_id: str | None = None                              # 담당자 필터
    state_name: str | None = None                               # state 이름 필터 (e.g. "In Progress")
    first: int = 20                                             # 최대 건수


@dataclass
class LinearReadOutput:
    # [{id, identifier, title, url, priority, state, assignee, created_at}]
    issues: list[dict[str, Any]]
    count: int


class LinearReadNode(BaseNode[LinearReadInput, LinearReadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Linear 이슈 조회",
        category="integration",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = LinearReadInput
    output_schema = LinearReadOutput

    async def process(self, input: LinearReadInput, context: NodeContext) -> LinearReadOutput:
        # connection_token = Linear API key (Authorization 헤더에 그대로).
        if not context.connection_token:
            raise ValidationError("linear_read는 credential(Linear API key)이 필요하다")

        filter_obj: dict[str, Any] = {}
        if input.team_id:
            filter_obj["team"] = {"id": {"eq": input.team_id}}
        if input.assignee_id:
            filter_obj["assignee"] = {"id": {"eq": input.assignee_id}}
        if input.state_name:
            filter_obj["state"] = {"name": {"eq": input.state_name}}

        payload = {
            "query": _ISSUES_QUERY,
            "variables": {"filter": filter_obj or None, "first": input.first},
        }
        headers = {"Authorization": context.connection_token, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_LINEAR_API_URL, json=payload, headers=headers)

        data = response.json()
        if data.get("errors"):
            raise ExecutionError(f"Linear GraphQL 오류: {data['errors']}")
        nodes = ((data.get("data") or {}).get("issues") or {}).get("nodes", [])
        issues = [
            {
                "id": n.get("id", ""),
                "identifier": n.get("identifier", ""),
                "title": n.get("title", ""),
                "url": n.get("url", ""),
                "priority": n.get("priority", 0),
                "state": (n.get("state") or {}).get("name", ""),
                "assignee": (n.get("assignee") or {}).get("name", ""),
                "created_at": n.get("createdAt", ""),
            }
            for n in nodes
        ]
        return LinearReadOutput(issues=issues, count=len(issues))


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Linear 이슈 조회",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "team_id": {"type": ["string", "null"]},
                "assignee_id": {"type": ["string", "null"]},
                "state_name": {"type": ["string", "null"]},
                "first": {"type": "integer", "default": 20},
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "issues": {"type": "array", "items": {"type": "object"}},
                "count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["linear"],
        description="Linear 이슈 목록 조회 (GraphQL issues). API key 자격증명 필요",
        is_mvp=True,
        service_type="linear",
    )
