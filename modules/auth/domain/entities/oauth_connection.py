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
    # ADR-0027 settings 목록 display: 서비스측 안정 식별자(google=sub/slack=team_id)와
    # 표시명(google=email/slack=workspace). 미확보 경로는 None, 다음 connect/refresh 시 backfill.
    account_id: str | None = None
    display_name: str | None = None
    is_active: bool = True
    connected_at: UtcDatetime
    last_refreshed_at: UtcDatetime | None = None

    def revoke(self) -> None:
        self.is_active = False
