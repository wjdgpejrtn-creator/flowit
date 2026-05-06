from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class OAuthConnection(BaseModel):
    model_config = ConfigDict(frozen=True)

    oauth_id: UUID  # == credential_id
    user_id: UUID
    service: Literal["google", "slack"]
    encrypted_access_token: bytes
    encrypted_refresh_token: bytes
    scopes: list[str]
    token_expires_at: Optional[datetime] = None
    is_revoked: bool = False
    created_at: datetime
