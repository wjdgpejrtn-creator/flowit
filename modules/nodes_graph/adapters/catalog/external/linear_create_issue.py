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

_NODE_TYPE = "linear_create_issue"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_LINEAR_API_URL = "https://api.linear.app/graphql"
_TIMEOUT_SECONDS = 30
_ISSUE_CREATE_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier url title state { name } createdAt }
  }
}
""".strip()


@dataclass
class LinearCreateIssueInput:
    team_id: str  # Linear 팀 ID
    title: str
    description: str = ""  # Markdown
    priority: int = 0  # 0(없음) | 1(긴급) | 2(높음) | 3(중간) | 4(낮음)
    assignee_id: str | None = None
    label_ids: list[str] = field(default_factory=list)
    project_id: str | None = None
    state_id: str | None = None  # 워크플로우 state. 미지정 시 backlog
    due_date: str | None = None  # ISO 8601 date


@dataclass
class LinearCreateIssueOutput:
    issue_id: str
    identifier: str  # e.g. "ENG-123"
    url: str
    title: str
    state: str
    created_at: str


class LinearCreateIssueNode(BaseNode[LinearCreateIssueInput, LinearCreateIssueOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Linear 이슈 생성",
        category="integration",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = LinearCreateIssueInput
    output_schema = LinearCreateIssueOutput

    async def process(self, input: LinearCreateIssueInput, context: NodeContext) -> LinearCreateIssueOutput:
        # connection_token = Linear API key (Authorization 헤더에 그대로).
        if not context.connection_token:
            raise ValidationError("linear_create_issue는 credential(Linear API key)이 필요하다")

        issue_input: dict[str, Any] = {
            "teamId": input.team_id,
            "title": input.title,
            "description": input.description,
            "priority": input.priority,
        }
        if input.assignee_id:
            issue_input["assigneeId"] = input.assignee_id
        if input.label_ids:
            issue_input["labelIds"] = input.label_ids
        if input.project_id:
            issue_input["projectId"] = input.project_id
        if input.state_id:
            issue_input["stateId"] = input.state_id
        if input.due_date:
            issue_input["dueDate"] = input.due_date

        payload = {"query": _ISSUE_CREATE_MUTATION, "variables": {"input": issue_input}}
        headers = {
            "Authorization": context.connection_token,
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_LINEAR_API_URL, json=payload, headers=headers)

        data = response.json()
        if data.get("errors"):
            raise ExecutionError(f"Linear GraphQL 오류: {data['errors']}")
        result = (data.get("data") or {}).get("issueCreate") or {}
        if not result.get("success") or not result.get("issue"):
            raise ExecutionError(f"Linear issueCreate 실패: {data}")

        issue = result["issue"]
        return LinearCreateIssueOutput(
            issue_id=issue["id"],
            identifier=issue["identifier"],
            url=issue["url"],
            title=issue["title"],
            state=(issue.get("state") or {}).get("name", ""),
            created_at=issue["createdAt"],
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Linear 이슈 생성",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "team_id": {
                    "type": "string",
                    "description": '이슈를 생성할 Linear 팀 ID. 팀 설정 > General에서 확인. 예: "a1b2c3d4-..."',
                },
                "title": {"type": "string", "description": "이슈 제목"},
                "description": {"type": "string", "description": "이슈 본문(Markdown 지원, 선택)"},
                "priority": {
                    "type": "integer",
                    "enum": [0, 1, 2, 3, 4],
                    "default": 0,
                    "description": "우선순위. 0=없음, 1=긴급, 2=높음, 3=보통, 4=낮음. 기본값 0",
                },
                "assignee_id": {"type": ["string", "null"], "description": "담당자 사용자 ID(선택)"},
                "label_ids": {"type": "array", "items": {"type": "string"}, "description": "적용할 라벨 ID 목록(선택)"},
                "project_id": {"type": ["string", "null"], "description": "연결할 프로젝트 ID(선택)"},
                "state_id": {"type": ["string", "null"], "description": "초기 상태(워크플로우 단계) ID(선택)"},
                "due_date": {
                    "type": ["string", "null"],
                    "format": "date",
                    "description": '마감일(YYYY-MM-DD, 선택). 예: "2026-06-30"',
                },
            },
            "required": ["team_id", "title"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "issue_id": {"type": "string"},
                "identifier": {"type": "string"},
                "url": {"type": "string"},
                "title": {"type": "string"},
                "state": {"type": "string"},
                "created_at": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["linear"],
        description="Linear에 이슈 생성 (GraphQL issueCreate). API key 자격증명 필요",
        is_mvp=True,
        service_type="linear",
    )
