from __future__ import annotations

import base64
from dataclasses import dataclass
from uuid import uuid5

import httpx
from common_schemas import NodeContext
from common_schemas.enums import RiskLevel
from common_schemas.exceptions import ExecutionError, ValidationError

from ....domain.catalog._catalog_ns import _CATALOG_NS
from ....domain.entities.base_node import BaseNode
from ....domain.entities.node_definition import NodeDefinition
from ....domain.entities.node_metadata import NodeMetadata

_NODE_TYPE = "google_drive_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_TIMEOUT_SECONDS = 60


@dataclass
class GoogleDriveReadInput:
    file_id: str  # Drive 파일 ID
    as_text: bool = False  # True이면 텍스트 디코딩(utf-8)된 content 반환
    export_mime_type: str | None = None  # Google Docs/Sheets 등 네이티브 포맷 export 시 지정


@dataclass
class GoogleDriveReadOutput:
    file_id: str
    name: str
    mime_type: str
    size: int  # 바이트 단위 (export 시 0 가능)
    content_base64: str  # 바이너리 base64. as_text=True여도 함께 반환
    text: str | None  # as_text=True일 때만 채워짐


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

    async def process(self, input: GoogleDriveReadInput, context: NodeContext) -> GoogleDriveReadOutput:
        # connection_token = Google OAuth access token. files.get 메타데이터 + 본문 다운로드.
        if not context.connection_token:
            raise ValidationError("google_drive_read는 credential(Google OAuth 토큰)이 필요하다")

        headers = {"Authorization": f"Bearer {context.connection_token}"}
        base = f"https://www.googleapis.com/drive/v3/files/{input.file_id}"
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            meta_resp = await client.get(base, params={"fields": "id,name,mimeType,size"}, headers=headers)
            if meta_resp.status_code >= 400:
                raise ExecutionError(f"Google Drive API 오류 {meta_resp.status_code}: {meta_resp.text[:200]}")
            meta = meta_resp.json()

            # Google 네이티브 문서(Docs/Sheets 등)는 export, 일반 파일은 alt=media 다운로드.
            if input.export_mime_type:
                content_resp = await client.get(
                    f"{base}/export", params={"mimeType": input.export_mime_type}, headers=headers
                )
            else:
                content_resp = await client.get(base, params={"alt": "media"}, headers=headers)
            if content_resp.status_code >= 400:
                raise ExecutionError(
                    f"Google Drive 다운로드 오류 {content_resp.status_code}: {content_resp.text[:200]}"
                )
            raw = content_resp.content

        text = raw.decode("utf-8", errors="replace") if input.as_text else None
        return GoogleDriveReadOutput(
            file_id=input.file_id,
            name=meta.get("name", ""),
            mime_type=meta.get("mimeType", ""),
            size=int(meta.get("size", 0) or 0),
            content_base64=base64.b64encode(raw).decode(),
            text=text,
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
                "file_id": {
                    "type": "string",
                    "description": '다운로드할 Drive 파일 ID. 파일 URL의 /d/ 뒤 문자열. 예: "1AbC...xyz"',
                },
                "as_text": {
                    "type": "boolean",
                    "default": False,
                    "description": "true면 결과를 텍스트로 반환. 기본값 false",
                },
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
