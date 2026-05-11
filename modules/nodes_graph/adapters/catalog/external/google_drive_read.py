from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "google_drive_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class GoogleDriveReadInput:
    file_id: str                                    # Drive 파일 ID
    as_text: bool = False                           # True이면 텍스트 디코딩(utf-8)된 content 반환
    export_mime_type: str | None = None             # Google Docs/Sheets 등 네이티브 포맷 export 시 지정


@dataclass
class GoogleDriveReadOutput:
    file_id: str
    name: str
    mime_type: str
    size: int                                       # 바이트 단위 (export 시 0 가능)
    content_base64: str                             # 바이너리 base64. as_text=True여도 함께 반환
    text: str | None                                # as_text=True일 때만 채워짐


class GoogleDriveReadNode(BaseNode[GoogleDriveReadInput, GoogleDriveReadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Google Drive 파일 읽기",
        category="integration",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = GoogleDriveReadInput
    output_schema = GoogleDriveReadOutput

    async def process(self, input: GoogleDriveReadInput) -> GoogleDriveReadOutput:
        raise NotImplementedError(
            "외부 서비스 호출은 REQ-005 toolset connector를 통해 처리. "
            "OAuth credential 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Google Drive 파일 읽기",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "as_text": {"type": "boolean", "default": False},
                "export_mime_type": {"type": ["string", "null"], "description": "Google Docs/Sheets export 포맷"},
            },
            "required": ["file_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "name": {"type": "string"},
                "mime_type": {"type": "string"},
                "size": {"type": "integer"},
                "content_base64": {"type": "string"},
                "text": {"type": ["string", "null"]},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["google"],
        description="Google Drive에서 파일 다운로드 (files.get + media). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
