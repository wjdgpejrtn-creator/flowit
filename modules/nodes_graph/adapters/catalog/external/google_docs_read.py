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

_NODE_TYPE = "google_docs_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_DOCS_API = "https://docs.googleapis.com/v1/documents"
_TIMEOUT_SECONDS = 60


def _extract_text(doc: dict[str, Any]) -> str:
    """문서 body.content의 paragraph textRun을 순서대로 이어 평문 추출."""
    parts: list[str] = []
    for element in doc.get("body", {}).get("content", []):
        paragraph = element.get("paragraph")
        if not paragraph:
            continue
        for run in paragraph.get("elements", []):
            text_run = run.get("textRun")
            if text_run and text_run.get("content"):
                parts.append(text_run["content"])
    return "".join(parts)


@dataclass
class GoogleDocsReadInput:
    document_id: str


@dataclass
class GoogleDocsReadOutput:
    document_id: str
    title: str
    text: str                                                   # 평문 본문 (개행 보존)
    revision_id: str


class GoogleDocsReadNode(BaseNode[GoogleDocsReadInput, GoogleDocsReadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Google Docs 읽기",
        category="integration",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = GoogleDocsReadInput
    output_schema = GoogleDocsReadOutput

    async def process(self, input: GoogleDocsReadInput, context: NodeContext) -> GoogleDocsReadOutput:
        # connection_token = Google OAuth access token. Docs documents.get → 본문 평문 추출.
        if not context.connection_token:
            raise ValidationError("google_docs_read는 credential(Google OAuth 토큰)이 필요하다")

        headers = {"Authorization": f"Bearer {context.connection_token}"}
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{_DOCS_API}/{input.document_id}", headers=headers)

        if response.status_code >= 400:
            raise ExecutionError(
                f"Google Docs API 오류 {response.status_code}: {response.text[:200]}"
            )

        doc = response.json()
        return GoogleDocsReadOutput(
            document_id=doc.get("documentId", input.document_id),
            title=doc.get("title", ""),
            text=_extract_text(doc),
            revision_id=doc.get("revisionId", ""),
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Google Docs 읽기",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
            },
            "required": ["document_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "title": {"type": "string"},
                "text": {"type": "string"},
                "revision_id": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["google"],
        description="Google Docs 문서 본문 평문 읽기 (documents.get). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
