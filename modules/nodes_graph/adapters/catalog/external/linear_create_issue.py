from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid5

from common_schemas import NodeContext
from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "linear_create_issue"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class LinearCreateIssueInput:
    team_id: str                                                # Linear 팀 ID
    title: str
    description: str = ""                                       # Markdown
    priority: int = 0                                           # 0(없음) | 1(긴급) | 2(높음) | 3(중간) | 4(낮음)
    assignee_id: str | None = None
    label_ids: list[str] = field(default_factory=list)
    project_id: str | None = None
    state_id: str | None = None                                 # 워크플로우 state. 미지정 시 backlog
    due_date: str | None = None                                 # ISO 8601 date


@dataclass
class LinearCreateIssueOutput:
    issue_id: str
    identifier: str                                             # e.g. "ENG-123"
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
        raise NotImplementedError(
            "Linear API 호출은 REQ-005 toolset connector를 통해 처리. "
            "API key 주입은 REQ-002 CredentialInjectionService 담당."
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
                "team_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "integer", "enum": [0, 1, 2, 3, 4], "default": 0},
                "assignee_id": {"type": ["string", "null"]},
                "label_ids": {"type": "array", "items": {"type": "string"}},
                "project_id": {"type": ["string", "null"]},
                "state_id": {"type": ["string", "null"]},
                "due_date": {"type": ["string", "null"], "format": "date"},
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
