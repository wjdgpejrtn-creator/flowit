from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "onedrive_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class OneDriveReadInput:
    item_id: str | None = None                      # OneDrive item ID. path와 둘 중 하나 필수
    path: str | None = None                         # 사용자 루트 기준 경로 (e.g. "/Documents/report.pdf")
    as_text: bool = False                           # True이면 utf-8 디코딩된 text 함께 반환
    drive_id: str | None = None                     # 다른 사용자/사이트 드라이브 지정 시


@dataclass
class OneDriveReadOutput:
    item_id: str
    name: str
    mime_type: str
    size: int
    content_base64: str
    text: str | None
    web_url: str                                    # OneDrive 미리보기 링크


class OneDriveReadNode(BaseNode[OneDriveReadInput, OneDriveReadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="OneDrive 파일 읽기",
        category="데이터 소스",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = OneDriveReadInput
    output_schema = OneDriveReadOutput

    async def process(self, input: OneDriveReadInput) -> OneDriveReadOutput:
        raise NotImplementedError(
            "외부 서비스 호출은 REQ-005 toolset connector를 통해 처리. "
            "OAuth credential 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="OneDrive 파일 읽기",
        category="데이터 소스",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "item_id": {"type": ["string", "null"], "description": "OneDrive item ID"},
                "path": {"type": ["string", "null"], "description": "사용자 루트 기준 경로"},
                "as_text": {"type": "boolean", "default": False},
                "drive_id": {"type": ["string", "null"]},
            },
            "oneOf": [
                {"required": ["item_id"]},
                {"required": ["path"]},
            ],
        },
        output_schema={
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "name": {"type": "string"},
                "mime_type": {"type": "string"},
                "size": {"type": "integer"},
                "content_base64": {"type": "string"},
                "text": {"type": ["string", "null"]},
                "web_url": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["microsoft"],
        description="OneDrive에서 파일 다운로드 (Microsoft Graph /drive/items/{id}/content). Microsoft OAuth 자격증명 필요",
        is_mvp=True,
        service_type="microsoft_365",
    )
