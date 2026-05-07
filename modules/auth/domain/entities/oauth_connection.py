from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel


class OAuthConnection(BaseModel):
    oauth_id: UUID
    user_id: UUID
    service: Literal["google", "slack"]
    credential_id: UUID
    access_token_encrypted: bytes
    refresh_token_encrypted: bytes | None = None
    scopes: list[str]
    is_active: bool = True
    connected_at: AwareDatetime
    last_refreshed_at: AwareDatetime | None = None

    def revoke(self) -> None:
        self.is_active = False
