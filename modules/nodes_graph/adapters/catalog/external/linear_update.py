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

_NODE_TYPE = "linear_update"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_LINEAR_API_URL = "https://api.linear.app/graphql"
_TIMEOUT_SECONDS = 30
_ISSUE_UPDATE_MUTATION = """
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id identifier url title state { name } updatedAt }
  }
}
""".strip()


@dataclass
class LinearUpdateInput:
    issue_id: str                                               # 수정할 이슈 ID
    title: str | None = None
    description: str | None = None                              # Markdown
    priority: int | None = None                                # 0~4
    assignee_id: str | None = None
    state_id: str | None = None                                # 워크플로우 state 전환
    label_ids: list[str] = field(default_factory=list)


@dataclass
class LinearUpdateOutput:
    issue_id: str
    identifier: str
    url: str
    title: str
    state: str
    updated_at: str


class LinearUpdateNode(BaseNode[LinearUpdateInput, LinearUpdateOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Linear 이슈 수정",
        category="integration",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = LinearUpdateInput
    output_schema = LinearUpdateOutput

    async def process(self, input: LinearUpdateInput, context: NodeContext) -> LinearUpdateOutput:
        # connection_token = Linear API key (Authorization 헤더에 그대로).
        if not context.connection_token:
            raise ValidationError("linear_update는 credential(Linear API key)이 필요하다")

        update_input: dict[str, Any] = {}
        if input.title is not None:
            update_input["title"] = input.title
        if input.description is not None:
            update_input["description"] = input.description
        if input.priority is not None:
            update_input["priority"] = input.priority
        if input.assignee_id:
            update_input["assigneeId"] = input.assignee_id
        if input.state_id:
            update_input["stateId"] = input.state_id
        if input.label_ids:
            update_input["labelIds"] = input.label_ids
        if not update_input:
            raise ValidationError("linear_update는 수정할 필드가 최소 1개 필요하다")

        payload = {
            "query": _ISSUE_UPDATE_MUTATION,
            "variables": {"id": input.issue_id, "input": update_input},
        }
        headers = {"Authorization": context.connection_token, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_LINEAR_API_URL, json=payload, headers=headers)

        data = response.json()
        if data.get("errors"):
            raise ExecutionError(f"Linear GraphQL 오류: {data['errors']}")
        result = (data.get("data") or {}).get("issueUpdate") or {}
        if not result.get("success") or not result.get("issue"):
            raise ExecutionError(f"Linear issueUpdate 실패: {data}")

        issue = result["issue"]
        return LinearUpdateOutput(
            issue_id=issue["id"],
            identifier=issue["identifier"],
            url=issue["url"],
            title=issue["title"],
            state=(issue.get("state") or {}).get("name", ""),
            updated_at=issue.get("updatedAt", ""),
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Linear 이슈 수정",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "title": {"type": ["string", "null"]},
                "description": {"type": ["string", "null"]},
                "priority": {"type": ["integer", "null"], "enum": [0, 1, 2, 3, 4, None]},
                "assignee_id": {"type": ["string", "null"]},
                "state_id": {"type": ["string", "null"]},
                "label_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["issue_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "identifier": {"type": "string"},
                "url": {"type": "string"},
                "title": {"type": "string"},
                "state": {"type": "string"},
                "updated_at": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["linear"],
        description="Linear 이슈 수정 (GraphQL issueUpdate — state/담당자/우선순위 등). API key 자격증명 필요",
        is_mvp=True,
        service_type="linear",
    )
