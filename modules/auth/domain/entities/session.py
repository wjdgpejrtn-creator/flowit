from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel


class Session(BaseModel):
    session_id: UUID
    user_id: UUID
    session_hash: str
    expires_at: UtcDatetime
    is_revoked: bool = False
    created_at: UtcDatetime
    device_info: str | None = None

    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at

    def revoke(self) -> None:
        self.is_revoked = True
