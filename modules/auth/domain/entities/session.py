from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class Session(BaseModel):
    session_id: UUID
    user_id: UUID
    session_hash: str
    expires_at: datetime
    is_revoked: bool = False
    created_at: datetime
    device_info: Optional[str] = None

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at

    def revoke(self) -> None:
        self.is_revoked = True
