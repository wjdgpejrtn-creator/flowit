from __future__ import annotations

import base64
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

_NODE_TYPE = "google_drive_upload"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_TIMEOUT_SECONDS = 120  # 업로드는 느릴 수 있음


@dataclass
class GoogleDriveUploadInput:
    name: str                                                   # 업로드 파일명
    content_base64: str                                         # 파일 바이너리 base64
    mime_type: str = "text/plain"
    folder_id: str | None = None                                # 부모 폴더 ID (미지정 시 루트)


@dataclass
class GoogleDriveUploadOutput:
    file_id: str
    name: str
    mime_type: str
    web_view_link: str                                          # https://drive.google.com/file/d/...


class GoogleDriveUploadNode(BaseNode[GoogleDriveUploadInput, GoogleDriveUploadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Google Drive 업로드",
        category="integration",
        risk_level=RiskLevel.HIGH,
        is_mvp=True,
    )
    input_schema = GoogleDriveUploadInput
    output_schema = GoogleDriveUploadOutput

    async def process(self, input: GoogleDriveUploadInput, context: NodeContext) -> GoogleDriveUploadOutput:
        # connection_token = Google OAuth access token. 2-step: files.create(메타) → media PATCH 업로드.
        # multipart/related 수기 조립 대신 메타 생성 + 미디어 업데이트로 분리(가독성·견고성).
        if not context.connection_token:
            raise ValidationError("google_drive_upload는 credential(Google OAuth 토큰)이 필요하다")

        try:
            raw = base64.b64decode(input.content_base64)
        except (ValueError, TypeError) as exc:
            raise ValidationError("content_base64가 유효한 base64가 아니다") from exc

        bearer = {"Authorization": f"Bearer {context.connection_token}"}
        metadata: dict[str, Any] = {"name": input.name, "mimeType": input.mime_type}
        if input.folder_id:
            metadata["parents"] = [input.folder_id]

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            meta_resp = await client.post(
                "https://www.googleapis.com/drive/v3/files",
                json=metadata,
                headers={**bearer, "Content-Type": "application/json"},
            )
            if meta_resp.status_code >= 400:
                raise ExecutionError(
                    f"Google Drive API 오류 {meta_resp.status_code}: {meta_resp.text[:200]}"
                )
            file_id = meta_resp.json().get("id", "")

            media_resp = await client.patch(
                f"https://www.googleapis.com/upload/drive/v3/files/{file_id}",
                params={"uploadType": "media", "fields": "id,name,mimeType,webViewLink"},
                content=raw,
                headers={**bearer, "Content-Type": input.mime_type},
            )
            if media_resp.status_code >= 400:
                raise ExecutionError(
                    f"Google Drive 업로드 오류 {media_resp.status_code}: {media_resp.text[:200]}"
                )
            data = media_resp.json()

        return GoogleDriveUploadOutput(
            file_id=data.get("id", file_id),
            name=data.get("name", input.name),
            mime_type=data.get("mimeType", input.mime_type),
            web_view_link=data.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view"),
        )


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Google Drive 업로드",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "content_base64": {"type": "string"},
                "mime_type": {"type": "string", "default": "text/plain"},
                "folder_id": {"type": ["string", "null"]},
            },
            "required": ["name", "content_base64"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "file_id": {"type": "string"},
                "name": {"type": "string"},
                "mime_type": {"type": "string"},
                "web_view_link": {"type": "string"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.HIGH,
        required_connections=["google"],
        description="Google Drive에 파일 업로드 (files.create + media). Google OAuth 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
