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

_NODE_TYPE = "gmail_read"
_NODE_ID = uuid5(_CATALOG_NS, _NODE_TYPE)
_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
_TIMEOUT_SECONDS = 60
_WANTED_HEADERS = ("Subject", "From", "Date")


def _header(headers: list[dict[str, Any]], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


@dataclass
class GmailReadInput:
    query: str = ""                                 # Gmail 검색 쿼리 (e.g. "from:boss is:unread")
    max_results: int = 10
    label_ids: list[str] = field(default_factory=list)  # e.g. ["INBOX", "UNREAD"]


@dataclass
class GmailReadOutput:
    messages: list[dict[str, Any]]                  # [{id, thread_id, subject, from, date, snippet}]
    count: int


class GmailReadNode(BaseNode[GmailReadInput, GmailReadOutput]):
    metadata = NodeMetadata(
        node_id=_NODE_ID,
        name="Gmail 메일 읽기",
        category="integration",
        risk_level=RiskLevel.MEDIUM,
        is_mvp=True,
    )
    input_schema = GmailReadInput
    output_schema = GmailReadOutput

    async def process(self, input: GmailReadInput, context: NodeContext) -> GmailReadOutput:
        # connection_token = Google OAuth access token. messages.list → 각 id의 metadata.get.
        if not context.connection_token:
            raise ValidationError("gmail_read는 credential(Google OAuth 토큰)이 필요하다")

        headers = {"Authorization": f"Bearer {context.connection_token}"}
        list_params: dict[str, Any] = {"maxResults": input.max_results}
        if input.query:
            list_params["q"] = input.query
        if input.label_ids:
            list_params["labelIds"] = input.label_ids

        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            list_resp = await client.get(_GMAIL_BASE, params=list_params, headers=headers)
            if list_resp.status_code >= 400:
                raise ExecutionError(
                    f"Gmail API 오류 {list_resp.status_code}: {list_resp.text[:200]}"
                )
            ids = [m.get("id") for m in list_resp.json().get("messages", []) if m.get("id")]

            messages: list[dict[str, Any]] = []
            for msg_id in ids:
                detail_resp = await client.get(
                    f"{_GMAIL_BASE}/{msg_id}",
                    params={"format": "metadata", "metadataHeaders": list(_WANTED_HEADERS)},
                    headers=headers,
                )
                if detail_resp.status_code >= 400:
                    raise ExecutionError(
                        f"Gmail API 오류 {detail_resp.status_code}: {detail_resp.text[:200]}"
                    )
                detail = detail_resp.json()
                hdrs = detail.get("payload", {}).get("headers", [])
                messages.append({
                    "id": detail.get("id", msg_id),
                    "thread_id": detail.get("threadId", ""),
                    "subject": _header(hdrs, "Subject"),
                    "from": _header(hdrs, "From"),
                    "date": _header(hdrs, "Date"),
                    "snippet": detail.get("snippet", ""),
                })

        return GmailReadOutput(messages=messages, count=len(messages))


def get_node_definition() -> NodeDefinition:
    return NodeDefinition(
        node_id=_NODE_ID,
        node_type=_NODE_TYPE,
        name="Gmail 메일 읽기",
        category="integration",
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Gmail 검색 쿼리 (예: from:boss is:unread)"},
                "max_results": {"type": "integer", "default": 10},
                "label_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
        },
        output_schema={
            "type": "object",
            "properties": {
                "messages": {"type": "array", "items": {"type": "object"}},
                "count": {"type": "integer"},
            },
        },
        parameter_schema={},
        risk_level=RiskLevel.MEDIUM,
        required_connections=["google"],
        description="Gmail 인박스 메일 조회 (messages.list + metadata.get). Google OAuth(readonly) 자격증명 필요",
        is_mvp=True,
        service_type="google_workspace",
    )
