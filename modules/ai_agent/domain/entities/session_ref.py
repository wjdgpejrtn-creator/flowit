from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from common_schemas import UtcDatetime


class SessionRef(BaseModel):
    """세션 인덱스 항목 — GCS index.json 한 줄에 해당."""

    session_id: UUID
    user_id: UUID
    workflow_id: UUID | None = None
    created_at: UtcDatetime
    message_preview: str = ""
