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

_NODE_TYPE = "google_docs_write"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_DOCS_API = "https://docs.googleapis.com/v1/documents"
_TIMEOUT_SECONDS = 60


def _json_or_raise(response: httpx.Response, label: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise ExecutionError(f"Google Docs {label} 오류 {response.status_code}: {response.text[:200]}")
    return response.json()


def _doc_end_index(doc: dict[str, Any]) -> int:
    """문서 body의 마지막 구조 요소 endIndex — 본문 끝 인덱스."""
    content = doc.get("body", {}).get("content", [])
    return content[-1].get("endIndex", 1) if content else 1


def _build_requests(mode: str, content: str, doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Docs batchUpdate requests — append는 본문 끝 삽입, replace는 기존 본문 삭제 후 삽입."""
    end = _doc_end_index(doc)
    if mode == "replace":
        requests: list[dict[str, Any]] = []
        if end - 1 > 1:  # 기존 본문이 있으면 [1, end-1] 삭제 (마지막 개행은 보존)
            requests.append({"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end - 1}}})
        requests.append({"insertText": {"location": {"index": 1}, "text": content}})
        return requests
    # append — 본문 끝(최종 개행 직전)에 삽입
    return [{"insertText": {"location": {"index": max(end - 1, 1)}, "text": content}}]


@dataclass
class GoogleDocsWriteInput:
    """문서 생성 또는 기존 문서에 내용 추가/교체.

    - document_id가 None: 새 문서 생성 (title 필수)
    - document_id 지정: 기존 문서에 작업 (mode=append/replace)
    """

    title: str | None = None  # 새 문서 생성 시 필수
    content: str = ""  # 작성할 텍스트 (개행 보존)
    document_id: str | None = None  # 기존 문서 ID (수정 시)
    mode: str = "append"  # append | replace | create_only
    folder_id: str | None = None  # 생성 시 부모 폴더 (Drive)


@dataclass
class GoogleDocsWriteOutput:
    document_id: str
    revision_id: str
    web_link: str  # https://docs.google.com/document/d/...
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

    async def process(self, input: GoogleDocsWriteInput, context: NodeContext) -> GoogleDocsWriteOutput:
        # connection_token = Google OAuth access token. Docs documents.create + batchUpdate.
        if not context.connection_token:
            raise ValidationError("google_docs_write는 credential(Google OAuth 토큰)이 필요하다")
        if input.mode not in ("append", "replace", "create_only"):
            raise ValidationError(f"mode는 append/replace/create_only만 허용: {input.mode!r}")

        headers = {
            "Authorization": f"Bearer {context.connection_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            if input.document_id is None:
                if not input.title:
                    raise ValidationError("새 문서 생성 시 title이 필요하다")
                doc = _json_or_raise(
                    await client.post(_DOCS_API, json={"title": input.title}, headers=headers),
                    "documents.create",
                )
                document_id: str = doc["documentId"]
                if input.folder_id:  # 새 문서를 지정 폴더로 이동 (Drive files.update)
                    _json_or_raise(
                        await client.patch(
                            f"https://www.googleapis.com/drive/v3/files/{document_id}",
                            params={"addParents": input.folder_id},
                            json={},
                            headers=headers,
                        ),
                        "drive.files.update",
                    )
            else:
                document_id = input.document_id
                doc = _json_or_raise(
                    await client.get(f"{_DOCS_API}/{document_id}", headers=headers),
                    "documents.get",
                )

            title = doc.get("title", input.title or "")
            revision_id = doc.get("revisionId", "")

            if input.content and input.mode != "create_only":
                result = _json_or_raise(
                    await client.post(
                        f"{_DOCS_API}/{document_id}:batchUpdate",
                        json={"requests": _build_requests(input.mode, input.content, doc)},
                        headers=headers,
                    ),
                    "documents.batchUpdate",
                )
                revision_id = result.get("writeControl", {}).get("requiredRevisionId", revision_id)

        return GoogleDocsWriteOutput(
            document_id=document_id,
            revision_id=revision_id,
            web_link=f"https://docs.google.com/document/d/{document_id}/edit",
            title=title,
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
                "content": {"type": "string", "description": "문서에 쓸 내용"},
                "document_id": {"type": ["string", "null"], "description": "기존 문서 수정 시 지정"},
                "mode": {
                    "type": "string",
                    "enum": ["append", "replace", "create_only"],
                    "default": "append",
                    "description": "append=기존 문서에 추가, replace=내용 교체, create_only=새로 생성. 기본값 append",
                },
                "folder_id": {
                    "type": ["string", "null"],
                    "description": "새 문서를 생성할 Drive 폴더 ID(선택). 폴더 URL의 마지막 문자열",
                },
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
        description="Google Docs 문서 생성/내용 추가·교체 (documents.create + batchUpdate). OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
