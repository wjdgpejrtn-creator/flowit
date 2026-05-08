from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from common_schemas.types import UtcDatetime
from pydantic import BaseModel


class OAuthConnection(BaseModel):
    oauth_id: UUID
    user_id: UUID
    service: Literal["google", "slack"]
    credential_id: UUID
    access_token_encrypted: bytes
    refresh_token_encrypted: bytes | None = None
    scopes: list[str]
    is_active: bool = True
    connected_at: UtcDatetime
    last_refreshed_at: UtcDatetime | None = None

    def revoke(self) -> None:
        self.is_active = False
