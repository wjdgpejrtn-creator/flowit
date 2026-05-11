from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid5

from common_schemas.enums import RiskLevel

from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata
from ....domain.catalog._catalog_ns import _CATALOG_NS

_NODE_TYPE = "google_docs_write"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)


@dataclass
class GoogleDocsWriteInput:
    """문서 생성 또는 기존 문서에 내용 추가/교체.

    - document_id가 None: 새 문서 생성 (title 필수)
    - document_id 지정: 기존 문서에 작업 (mode=append/replace)
    """
    title: str | None = None                        # 새 문서 생성 시 필수
    content: str = ""                               # 작성할 텍스트 (개행 보존)
    document_id: str | None = None                  # 기존 문서 ID (수정 시)
    mode: str = "append"                            # append | replace | create_only
    folder_id: str | None = None                    # 생성 시 부모 폴더 (Drive)


@dataclass
class GoogleDocsWriteOutput:
    document_id: str
    revision_id: str
    web_link: str                                   # https://docs.google.com/document/d/...
    title: str


class GoogleDocsWriteNode(BaseNode[GoogleDocsWriteInput, GoogleDocsWriteOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Google Docs 작성",
        category="output",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = GoogleDocsWriteInput
    output_schema = GoogleDocsWriteOutput

    async def process(self, input: GoogleDocsWriteInput) -> GoogleDocsWriteOutput:
        raise NotImplementedError(
            "외부 서비스 호출은 REQ-005 toolset connector를 통해 처리. "
            "OAuth credential 주입은 REQ-002 CredentialInjectionService 담당."
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Google Docs 작성",
        category="output",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": ["string", "null"], "description": "새 문서 생성 시 필수"},
                "content": {"type": "string"},
                "document_id": {"type": ["string", "null"], "description": "기존 문서 수정 시 지정"},
                "mode": {
                    "type": "string",
                    "enum": ["append", "replace", "create_only"],
                    "default": "append",
                },
                "folder_id": {"type": ["string", "null"]},
            },
            "required": ["content"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "revision_id": {"type": "string"},
                "web_link": {"type": "string"},
                "title": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["google"],
        description="Google Docs 문서 생성 또는 내용 추가/교체 (Docs API documents.create + batchUpdate). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
